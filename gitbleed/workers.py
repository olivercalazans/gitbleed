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
import re
import requests
import traceback
import time
from contextlib      import closing
from requests_pkcs12 import Pkcs12Adapter

from check   import *
from display import Display
from helpers import *
from parser  import Arguments




class Worker(multiprocessing.Process):

    def __init__(
        self,
        pending_tasks : multiprocessing.Queue,
        tasks_done    : multiprocessing.Queue,
        args          : Arguments,
    ):
        super().__init__()
        self.daemon        : bool                  = True
        self.pending_tasks : multiprocessing.Queue = pending_tasks
        self.tasks_done    : multiprocessing.Queue = tasks_done
        self.args          : Arguments             = args



    def run(self):
        self.init(self.args)

        while True:
            task = self.pending_tasks.get(block=True)

            if task is None:  # end signal
                return

            try:
                result = self.do_task(task, self.args)
            except Exception:
                Display.warning(f"Task {task} raised exception:")
                traceback.print_exc()
                result = []

            if not isinstance(result, list):
                Display.warning(
                    f"do_task returned {type(result).__name__}, expected list"
                )
                result = []

            self.tasks_done.put(result)

    def init(self, args: Arguments):
        raise NotImplementedError

    def do_task(self, task, args: Arguments) -> list:
        raise NotImplementedError




class DownloadWorker(Worker):

    def init(self, args: Arguments):
        self._delay   : float            = args.delay
        self._session : requests.Session = requests.Session()

        self._session.verify = False
        self._configure_session(args)



    def _configure_session(self, args: Arguments):
        self._session.headers.clear()
        self._session.headers.update(args.http_headers)
        self._session.headers.pop("Accept-Encoding", None)

        if args.proxy:
            self._session.proxies = {
                "http":  args.proxy,
                "https": args.proxy,
            }

        if not args.cert_p12:
            self._session.mount(
                args.url,
                requests.adapters.HTTPAdapter(max_retries=args.retry),
            )
            return

        self._session.mount(
            args.url,
            Pkcs12Adapter(
                pkcs12_filename=args.cert_p12,
                pkcs12_password=args.cert_p12_pwd,
                max_retries=args.retry,
            ),
        )



    def _request(self, url: str, **kwargs) -> requests.Response:
        response = self._session.get(url, **kwargs)

        if self._delay > 0:
            time.sleep(self._delay)

        return response



    def do_task(self, filepath: str, args: Arguments) -> list:
        if os.path.isfile(os.path.join(args.directory, filepath)):
            print(f"[---] Already downloaded {args.url}/{filepath}", flush=True)
            return []

        with closing(
            self._request(
                f"{args.url}/{filepath}",
                allow_redirects=False,
                stream=True,
                timeout=args.timeout,
            )
        ) as response:
            valid, display, error_msg = verify_response(response)

            if not valid:
                if display:
                    Display.warning(f"Invalid response from {response.url}: {error_msg}")
                return []

            abspath = os.path.abspath(os.path.join(args.directory, filepath))
            create_intermediate_dirs(abspath)
            write_stream_atomic(abspath, response.iter_content(4096))

            return []




class RecursiveDownloadWorker(DownloadWorker):

    def do_task(self, filepath: str, args: Arguments) -> list:
        if os.path.isfile(os.path.join(args.directory, filepath)):
            print(f"[---] Already downloaded {args.url}/{filepath}", flush=True)
            return []

        with closing(
            self._request(
                f"{args.url}/{filepath}",
                allow_redirects=False,
                stream=True,
                timeout=args.timeout,
            )
        ) as response:
            Display.response(response)

            if (
                response.status_code in (301, 302)
                and "Location" in response.headers
                and response.headers["Location"].endswith(filepath + "/")
            ):
                return [filepath + "/"]

            if filepath.endswith("/"):  # directory index
                if not is_html(response):
                    Display.warning(f"Expected HTML index at {response.url}")
                    return []

                return [
                    filepath + filename
                    for filename in get_indexed_files(response)
                ]

            valid, display, error_msg = verify_response(response)

            if not valid:
                if display:
                    Display.warning(f"Invalid response from {response.url}: {error_msg}")
                return []

            abspath = os.path.abspath(os.path.join(args.directory, filepath))
            create_intermediate_dirs(abspath)
            write_stream_atomic(abspath, response.iter_content(4096))

            return []




class FindRefsWorker(DownloadWorker):

    def do_task(self, filepath: str, args: Arguments) -> list:
        response = self._request(
            f"{args.url}/{filepath}",
            allow_redirects=False,
            timeout=args.timeout,
        )

        valid, display, error_msg = verify_response(response)

        if not valid:
            if display:
                Display.warning(f"Invalid response from {response.url}: {error_msg}")
            return []

        abspath = os.path.abspath(os.path.join(args.directory, filepath))
        create_intermediate_dirs(abspath)
        write_file_atomic(abspath, response.text, mode="w")

        tasks = []

        for ref in re.findall(
            r"(refs(/[a-zA-Z0-9\-\.\_\*]+)+)", response.text
        ):
            ref = ref[0]
            if not ref.endswith("*") and is_safe_path(ref):
                tasks.append(f".git/{ref}")
                tasks.append(f".git/logs/{ref}")

        return tasks




class FindObjectsWorker(DownloadWorker):

    def do_task(self, obj, args: Arguments) -> list:
        filepath = f".git/objects/{obj[:2]}/{obj[2:]}"

        if os.path.isfile(os.path.join(args.directory, filepath)):
            print(f"[---] Already downloaded {args.url}/{filepath}", flush=True)
        else:
            if not self._get_obj(filepath, args):
                return []

        try:
            abspath  = os.path.abspath(os.path.join(args.directory, filepath))
            obj_file = dulwich.objects.ShaFile.from_path(abspath)
            return get_referenced_sha1(obj_file)
        except Exception as e:
            Display.warning(f"Error while parsing file {filepath}: {e}")
            return []



    def _get_obj(self, filepath: str, args: Arguments) -> bool:
        response = self._request(
            f"{args.url}/{filepath}",
            allow_redirects=False,
            timeout=args.timeout,
        )

        valid, display, error_msg = verify_response(response)

        if not valid:
            if display:
                Display.warning(f"Invalid response from {response.url}: {error_msg}")
            return False

        abspath = os.path.abspath(os.path.join(args.directory, filepath))
        create_intermediate_dirs(abspath)
        write_stream_atomic(abspath, response.iter_content(4096))

        return True