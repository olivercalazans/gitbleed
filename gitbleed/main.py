# Copyright 2026 Oliver R. Calazans Jeronimo
# Modified from the original project git-dumper (Copyright (c) 2017 Maxime Arthaud)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import multiprocessing
import os
import queue
import re
import subprocess
import sys
import time
import dulwich.index
import dulwich.pack
import requests
import urllib3
from requests_pkcs12 import Pkcs12Adapter

from check   import is_html
from display import Display
from helpers import *
from parser  import Arguments, Parser
from workers import RecursiveDownloadWorker, DownloadWorker, FindRefsWorker, FindObjectsWorker



class GitBleed:

    __slots__ = ('_args', '_session', '_response', '_environment')

    def __init__(self):
        self._args        : Arguments         = None
        self._session     : requests.Session  = None
        self._response    : requests.Response = None
        self._environment : dict[str, str]    = None



    def execute(self):
        self._get_args()
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._create_session()
        self._find_base_url()
        self._try_to_connect()
        self._valid_response()
        self._setup_env_for_proxy()
        self._try_fast_dump()    # if successful, it stops here
        self._fetch_common_files()
        self._discover_references()
        self._fetch_git_packs()
        self._discover_and_fetch_objects()
        self._finalize_checkout()



    def _get_args(self):
        parser = Parser()
        parser.parse()
        self._args = parser.get_args()



    def _create_session(self):
        self._session         = requests.Session()
        self._session.verify  = False

        self._session.headers.update(self._args.http_headers)
        self._session.headers.pop("Accept-Encoding", None)
        self._configure_session()

        if os.listdir(self._args.directory):
            Display.warning(f"Destination '{self._args.directory}' is not empty")



    def _configure_session(self):
        if self._args.proxy:
            self._session.proxies = {
                "http":  self._args.proxy,
                "https": self._args.proxy,
            }

        if not self._args.cert_p12:
            self._session.mount(
                self._args.url,
                requests.adapters.HTTPAdapter(max_retries=self._args.retry),
            )
            return

        self._session.mount(
            self._args.url,
            Pkcs12Adapter(
                pkcs12_filename=self._args.cert_p12,
                pkcs12_password=self._args.cert_p12_pwd,
                max_retries=self._args.retry,
            ),
        )



    def _find_base_url(self):
        url: str = self._args.url

        url = url.rstrip("/")
        if url.endswith("HEAD"):
            url = url[:-4]

        url = url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]

        self._args.url = url.rstrip("/")



    def _try_to_connect(self):
        try:
            self._response = self._session.get(
                f"{self._args.url}/.git/HEAD",
                timeout=self._args.timeout,
            )
            time.sleep(self._args.delay)
        except Exception as e:
            Display.fatal(f"Unable to connect to {self._args.url}. Error: {e}")



    def _valid_response(self):
        valid, _, error_msg = verify_response(self._response)

        if self._response.status_code >= 400:
            Display.fatal("Target unreachable. Dumping stopped")

        elif self._response.status_code >= 300:
            Display.warning(f"Redirection required to {self._response.headers['Location']}")
            sys.exit(0)

        if not valid:
            Display.fatal(f"Invalid response from {self._response.url}: {error_msg}")

        if not re.match(r"^(ref:.*|[0-9a-f]{40}$)", self._response.text.strip()):
            Display.fatal(f"{self._response.url} is not a git HEAD file")



    def _setup_env_for_proxy(self):
        self._environment = os.environ.copy()

        if not self._args.proxy:
            return

        self._environment["ALL_PROXY"] = self._args.proxy
        self._environment["all_proxy"] = self._args.proxy



    def _try_fast_dump(self):
        Display.section("Trying fast dumping")

        response = self._session.get(f"{self._args.url}/.git/", allow_redirects=False)
        time.sleep(self._args.delay)

        Display.response(response)

        if (
            response.status_code != 200
            or not is_html(response)
            or "HEAD" not in get_indexed_files(response)
        ):
            return

        Display.section("Fetching .git recursively")
        self._process_tasks([".git/", ".gitignore"], RecursiveDownloadWorker)

        self._finalize_checkout()
        sys.exit(0)



    def _process_tasks(self, initial_tasks: list, worker, tasks_done=None):
        if not initial_tasks:
            return

        tasks_seen        = set(tasks_done) if tasks_done else set()
        pending_tasks     = multiprocessing.Queue()
        tasks_done        = multiprocessing.Queue()
        num_pending_tasks = 0

        for task in initial_tasks:
            assert task is not None
            if task not in tasks_seen:
                pending_tasks.put(task)
                num_pending_tasks += 1
                tasks_seen.add(task)

        processes = [worker(pending_tasks, tasks_done, self._args) for _ in range(self._args.jobs)]

        for p in processes:
            p.start()

        timed_out = False

        while num_pending_tasks > 0:
            try:
                task_result = tasks_done.get(block=True, timeout=60)
            except queue.Empty:
                Display.warning("Timeout waiting for workers; aborting")
                timed_out = True
                break

            num_pending_tasks -= 1

            for task in task_result:
                assert task is not None
                if task not in tasks_seen:
                    pending_tasks.put(task)
                    num_pending_tasks += 1
                    tasks_seen.add(task)

        if timed_out:
            for p in processes: p.terminate()
            for p in processes: p.join()
            return

        for _ in range(self._args.jobs):
            pending_tasks.put(None)

        for p in processes:
            p.join()



    UNSAFE = r"^\s*fsmonitor|sshcommand|askpass|editor|pager"

    def _sanitize_file(self, filepath=".git/config"):
        if not os.path.isfile(filepath):
            Display.warning(".git/config not found")
            return

        Display.section("Sanitizing .git/config")

        with open(filepath, 'r+') as f:
            content = f.read()
            modified_content = re.sub(self.UNSAFE, r'# \g<0>', content, flags=re.IGNORECASE)

            if content != modified_content:
                Display.warning(f"'{filepath}' file was altered")
                f.seek(0)
                f.write(modified_content)



    def _fetch_common_files(self):
        Display.section("Fetching common files")

        TASKS = [
            ".gitignore",
            ".git/COMMIT_EDITMSG",
            ".git/description",
            ".git/hooks/applypatch-msg.sample",
            ".git/hooks/commit-msg.sample",
            ".git/hooks/post-commit.sample",
            ".git/hooks/post-receive.sample",
            ".git/hooks/post-update.sample",
            ".git/hooks/pre-applypatch.sample",
            ".git/hooks/pre-commit.sample",
            ".git/hooks/pre-push.sample",
            ".git/hooks/pre-rebase.sample",
            ".git/hooks/pre-receive.sample",
            ".git/hooks/prepare-commit-msg.sample",
            ".git/hooks/update.sample",
            ".git/index",
            ".git/info/exclude",
            ".git/objects/info/packs",
        ]

        self._process_tasks(TASKS, DownloadWorker)



    def _discover_references(self):
        Display.section("Finding refs/")

        TASKS = [
            ".git/FETCH_HEAD",
            ".git/HEAD",
            ".git/ORIG_HEAD",
            ".git/config",
            ".git/info/refs",
            ".git/logs/HEAD",
            ".git/logs/refs/heads/main",
            ".git/logs/refs/heads/master",
            ".git/logs/refs/heads/staging",
            ".git/logs/refs/heads/production",
            ".git/logs/refs/heads/development",
            ".git/logs/refs/remotes/origin/HEAD",
            ".git/logs/refs/remotes/origin/main",
            ".git/logs/refs/remotes/origin/master",
            ".git/logs/refs/remotes/origin/staging",
            ".git/logs/refs/remotes/origin/production",
            ".git/logs/refs/remotes/origin/development",
            ".git/logs/refs/stash",
            ".git/packed-refs",
            ".git/refs/heads/main",
            ".git/refs/heads/master",
            ".git/refs/heads/staging",
            ".git/refs/heads/production",
            ".git/refs/heads/development",
            ".git/refs/remotes/origin/HEAD",
            ".git/refs/remotes/origin/main",
            ".git/refs/remotes/origin/master",
            ".git/refs/remotes/origin/staging",
            ".git/refs/remotes/origin/production",
            ".git/refs/remotes/origin/development",
            ".git/refs/stash",
            ".git/refs/wip/wtree/refs/heads/main",
            ".git/refs/wip/wtree/refs/heads/master",
            ".git/refs/wip/wtree/refs/heads/staging",
            ".git/refs/wip/wtree/refs/heads/production",
            ".git/refs/wip/wtree/refs/heads/development",
            ".git/refs/wip/index/refs/heads/main",
            ".git/refs/wip/index/refs/heads/master",
            ".git/refs/wip/index/refs/heads/staging",
            ".git/refs/wip/index/refs/heads/production",
            ".git/refs/wip/index/refs/heads/development",
        ]

        self._add_user_specified_branches(TASKS)
        self._process_tasks(TASKS, FindRefsWorker)



    def _add_user_specified_branches(self, tasks: list):
        if not self._args.branches:
            return

        for branch in self._args.branches:
            if not re.match(r'^[A-Za-z0-9\-\._]+$', branch):
                Display.warning(f"Ignoring invalid branch name '{branch}'")
                continue

            tasks.extend([
                f".git/logs/refs/heads/{branch}",
                f".git/refs/heads/{branch}",
                f".git/logs/refs/remotes/origin/{branch}",
                f".git/refs/remotes/origin/{branch}",
                f".git/refs/wip/wtree/refs/heads/{branch}",
                f".git/refs/wip/index/refs/heads/{branch}",
            ])



    def _fetch_git_packs(self):
        Display.section("Finding packs")
        tasks = []

        info_packs_path = os.path.join(
            self._args.directory, ".git", "objects", "info", "packs"
        )

        if os.path.exists(info_packs_path):
            with open(info_packs_path, "r") as f:
                info_packs = f.read()

            for sha1 in re.findall(r"pack-([a-f0-9]{40})\.pack", info_packs):
                tasks.append(".git/objects/pack/pack-%s.idx" % sha1)
                tasks.append(".git/objects/pack/pack-%s.pack" % sha1)

        self._process_tasks(tasks, DownloadWorker)



    def _discover_and_fetch_objects(self):
        Display.section("Finding objects")
        objs        = set()
        packed_objs = set()

        files = [
            os.path.join(self._args.directory, ".git", "packed-refs"),
            os.path.join(self._args.directory, ".git", "info", "refs"),
            os.path.join(self._args.directory, ".git", "FETCH_HEAD"),
            os.path.join(self._args.directory, ".git", "ORIG_HEAD"),
        ]

        self._collect_file_paths_from_git_subdir(files, "refs")
        self._collect_file_paths_from_git_subdir(files, "logs")
        self._extract_sha1_hashes_from_files(files, objs)
        self._parse_staging_area(objs)
        self._process_pack_files(packed_objs, objs)

        Display.section("Fetching objects")
        self._process_tasks(objs, FindObjectsWorker, tasks_done=packed_objs)



    def _collect_file_paths_from_git_subdir(self, files: list, subpath: str):
        base_path = os.path.join(self._args.directory, ".git", subpath)

        if not os.path.isdir(base_path):
            return

        for dirpath, _, filenames in os.walk(base_path):
            for filename in filenames:
                files.append(os.path.join(dirpath, filename))



    @staticmethod
    def _extract_sha1_hashes_from_files(files: list, objs: set):
        for filepath in files:
            if not os.path.isfile(filepath):
                continue

            try:
                with open(filepath, "r", encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue

            for match in re.findall(r"(^|\s)([a-f0-9]{40})($|\s)", content):
                objs.add(match[1])



    def _parse_staging_area(self, objs: set):
        index_path = os.path.join(self._args.directory, ".git", "index")

        if not os.path.exists(index_path):
            return

        try:
            index = dulwich.index.Index(index_path)
            for entry in index.iterobjects():
                objs.add(entry[1].decode())
        except Exception:
            pass



    def _process_pack_files(self, packed_objs: set, objs: set):
        pack_file_dir = os.path.join(self._args.directory, ".git", "objects", "pack")

        if not os.path.isdir(pack_file_dir):
            return

        for filename in os.listdir(pack_file_dir):
            if not filename.startswith("pack-") or not filename.endswith(".pack"):
                continue

            try:
                pack_data_path = os.path.join(pack_file_dir, filename)
                pack_idx_path  = os.path.join(pack_file_dir, filename[:-5] + ".idx")
                pack_data      = dulwich.pack.PackData(pack_data_path)
                pack_idx       = dulwich.pack.load_pack_index(pack_idx_path)
                pack           = dulwich.pack.Pack.from_objects(pack_data, pack_idx)

                for obj_file in pack.iterobjects():
                    packed_objs.add(obj_file.sha().hexdigest())
                    objs |= set(get_referenced_sha1(obj_file))

            except Exception:
                continue



    def _finalize_checkout(self):
        Display.section("Running git checkout")

        cwd = os.getcwd()
        try:
            os.chdir(self._args.directory)
            self._sanitize_file()

            subprocess.call(
                ["git", "checkout", "."],
                stderr=subprocess.DEVNULL,
                env=self._environment,
            )

        finally:
            os.chdir(cwd)
            Display.success(f"Repository saved to {self._args.directory}")




def main():
    try:
        git_looter = GitBleed()
        git_looter.execute()
        sys.exit(0)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        Display.fatal(f'{e}')



if __name__ == "__main__":
    main()
