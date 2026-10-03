from contextlib import closing
import argparse
import multiprocessing
import os
import re
import socket
import subprocess
import sys
import traceback
import urllib.parse
import urllib3
import bs4
import dulwich.index
import dulwich.objects
import dulwich.pack
import requests
import socks
import time
from dataclasses import dataclass
from requests_pkcs12 import Pkcs12Adapter



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
        if not self._args.client_cert_p12:
            self._session.mount(self._args.url, requests.adapters.HTTPAdapter(max_retries=self._args.retry))
            return
        
        self._session.mount(
            self._args.url, 
            Pkcs12Adapter(
                pkcs12_filename=self._args.client_cert_p12, 
                pkcs12_password=self._args.client_cert_p12_password,
                max_retries=self._args.retry,
            )
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
                timeout = self._args.timeout,
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
            Display.fatal(f"Invalid responde from {self._response.url}: {error_msg}")
       
        if not re.match(r"^(ref:.*|[0-9a-f]{40}$)", self._response.text.strip()):
            Display.fatal(f"{self._response.url} is not a git HEAD file")



    def _setup_env_for_proxy(self):
        self._environment = os.environ.copy()
        configured_proxy  = socks.getdefaultproxy()

        if configured_proxy is None:
            return
        
        proxy_types = ["http", "socks4h", "socks5h"]
        self._environment["ALL_PROXY"] = f"http.proxy={proxy_types[configured_proxy[0]]}://{configured_proxy[1]}:{configured_proxy[2]}"



    def _try_fast_dump(self):
        Display.section("Trying fast dumping")
        
        response = self._session.get(f"{self._args.url}/.git/", allow_redirects=False)
        time.sleep(self._args.delay)

        Display.response(response)

        if (
            response.status_code != 200 or 
            not is_html(response) or 
            "HEAD" not in get_indexed_files(response)
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

        # add all initial tasks in the queue
        for task in initial_tasks:
            assert task is not None

            if task not in tasks_seen:
                pending_tasks.put(task)
                num_pending_tasks += 1
                tasks_seen.add(task)

        # initialize processes
        processes = [worker(pending_tasks, tasks_done, self._args) for _ in range(self._args.jobs)]

        # launch them all
        for p in processes:
            p.start()

        # collect task results
        while num_pending_tasks > 0:
            task_result = tasks_done.get(block=True)
            num_pending_tasks -= 1

            for task in task_result:
                assert task is not None

                if task not in tasks_seen:
                    pending_tasks.put(task)
                    num_pending_tasks += 1
                    tasks_seen.add(task)


        # send termination signal (task=None)
        for _ in range(self._args.jobs):
            pending_tasks.put(None)

        for p in processes:
            p.join()
    

    

    UNSAFE=r"^\s*fsmonitor|sshcommand|askpass|editor|pager"

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
            ".git/refs/wip/index/refs/heads/development"
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

        # use .git/objects/info/packs to find packs
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

        # .git/packed-refs, .git/info/refs, .git/refs/*, .git/logs/*
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
            if not os.path.isfile(filepath):  # race condition
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
                pack_data      = dulwich.pack.PackData(pack_data_path, ...)
                pack_idx       = dulwich.pack.load_pack_index(pack_idx_path, ...)
                pack           = dulwich.pack.Pack.from_objects(pack_data, pack_idx)

                for obj_file in pack.iterobjects():
                    packed_objs.add(obj_file.sha().hexdigest())
                    objs |= set(get_referenced_sha1(obj_file))
            
            except Exception:
                continue



    def _finalize_checkout(self):
        Display.section("Running git checkout")
        os.chdir(self._args.directory)
        self._sanitize_file()

        # ignore errors
        subprocess.call(
            ["git", "checkout", "."],
            stderr=open(os.devnull, "wb"),
            env=self._environment
        )





@dataclass(slots=True)
class Arguments:
    client_cert_p12_password: str
    client_cert_p12 : str
    url             : str
    directory       : str
    proxy           : str
    jobs            : int
    retry           : int
    timeout         : int
    http_headers    : dict[str, str]
    branches        : list[str]
    delay           : float





class Parser:

    __slots__ = ('_args', '_parser')

    def __init__(self):
        self._args   : argparse.Namespace      = None
        self._parser : argparse.ArgumentParser = None

    
    
    def parse(self):
        self._create_args()
        self._args = self._parser.parse_args()
        self._valid_jobs()
        self._valid_retry()
        self._valid_timeout()
        self._valid_proxy()
        self._valid_certificate()
        self._valid_delay()
        self._create_dir()

    

    def _create_args(self):
        self._parser = argparse.ArgumentParser(
            usage="git-dumper [options] URL DIR",
            description="Dump a git repository from a website.",
        )
        self._parser.add_argument("url", metavar="URL", help="URL")
        self._parser.add_argument("directory", metavar="DIR", help="Output directory")
        self._parser.add_argument("--proxy", help="Use the specified proxy")
        self._parser.add_argument("--client-cert-p12", help="Client certificate in PKCS#12")
        self._parser.add_argument("--client-cert-p12-password", help="Password for the client certificate")
        self._parser.add_argument("-d", "--delay", type=float, default=0, help="Delay between requests")
        self._parser.add_argument(
            "-j", "--jobs", type=int, default=10,
            help="Number of simultaneous requests",
        )
        self._parser.add_argument(
            "-r", "--retry", type=int, default=3,
            help="Number of request attempts before giving up",
        )
        self._parser.add_argument(
            "-t", "--timeout", type=int, default=3,
            help="Maximum time in seconds before giving up",
        )
        self._parser.add_argument(
            "-u", "--user-agent", type=str,
            default="Mozilla/5.0 (Windows NT 10.0; rv:78.0) Gecko/20100101 Firefox/78.0",
            help="User-agent to use for requests",
        )
        self._parser.add_argument(
            "-H", "--header", type=str, action="append",
            help="Additional http headers, e.g `NAME=VALUE`",
        )
        self._parser.add_argument(
            "-b", "--branch", dest="branches", action="append",
            help="Additional branch names to check for, e.g. `-b dev -b prod`. The default branches (`main`, `master`, `staging`, `production`, `development`) are always checked.",
        )


    
    def _valid_jobs(self):
        if self._args.jobs < 1:
            self._parser.error(f"Invalid number of jobs, got {self._args.jobs}")



    def _valid_retry(self):
        if self._args.retry < 1:
            self._parser.error(f"Invalid number of retries, got {self._args.retry}")



    def _valid_timeout(self):
        if self._args.timeout < 1:
            self._parser.error(f"Invalid timeout, got {self._args.timeout}")

    

    def _valid_delay(self):
        if self._args.delay < 0:
            self._parser.error(f"Delay value cannot be negative. Got {self._args.delay}")



    def _valid_proxy(self):
        if self._args.proxy:
            proxy_valid = False

            for pattern, proxy_type in [
                (r"^socks5:(.*):(\d+)$", socks.PROXY_TYPE_SOCKS5),
                (r"^socks4:(.*):(\d+)$", socks.PROXY_TYPE_SOCKS4),
                (r"^http://(.*):(\d+)$", socks.PROXY_TYPE_HTTP),
                (r"^(.*):(\d+)$", socks.PROXY_TYPE_SOCKS5),
            ]:
                m = re.match(pattern, self._args.proxy)
                if m:
                    socks.setdefaultproxy(proxy_type, m.group(1), int(m.group(2)))
                    socket.socket = socks.socksocket
                    proxy_valid = True
                    break

            if not proxy_valid:
                self._parser.error(f"Invalid proxy, got {self._args.proxy}")

    

    def _create_dir(self):
        if not os.path.exists(self._args.directory):
            os.makedirs(self._args.directory)

        if not os.path.isdir(self._args.directory):
            self._parser.error(f"{self._args.directory} is not a directory")



    def _valid_certificate(self):
        if not self._args.client_cert_p12:
            return
        
        if not os.path.exists(self._args.client_cert_p12):
            self._parser.error(
                f"Client certificate {self._args.client_cert_p12} does not exist"
            )

        if not os.path.isfile(self._args.client_cert_p12):
            self._parser.error(
                f"Client certificate {self._args.client_cert_p12} is not a file"
            )

        if self._args.client_cert_p12_password is None:
            self._parser.error("Client certificate password is required")



    def _valid_headers(self) -> dict:
        http_headers = {
            "User-Agent": "curl/8.14.1",
            "Accept": "*/*",
        }
        
        if not self._args.header:
            return http_headers
        
        for header in self._args.header:
            tokens: list[str] = header.split("=", maxsplit=1)
            
            if len(tokens) != 2:
                self._parser.error(f"HTTP header must have the form NAME=VALUE, got {header}")
            
            name, value = tokens
            http_headers[name.strip()] = value.strip()
        
        return http_headers
    

    
    def get_args(self) -> Arguments:
        return Arguments(
            client_cert_p12_password = self._args.client_cert_p12_password,
            client_cert_p12 = self._args.client_cert_p12,
            directory       = self._args.directory,
            proxy           = self._args.proxy,
            url             = self._args.url,
            jobs            = self._args.jobs,
            retry           = self._args.retry,
            timeout         = self._args.timeout,
            http_headers    = self._valid_headers(),
            branches        = self._args.branches,
            delay           = self._args.delay,
        )




class Display:

    HTML: str = " [\033[34mHTML\033[0m] "

    @staticmethod
    def response(responde: requests.Response):
        code = responde.status_code

        if   code >= 400: x = f"\033[31m{code}\033[0m"   # red
        elif code >= 300: x = f"\033[33m{code}\033[0m"   # orange
        elif code >= 200: x = f"\033[32m{code}\033[0m"   # green
        else:             x = f"{code}"

        z = Display.HTML if is_html(responde) else ' '

        print(f"[{x}]{z}{responde.url}", flush=True)


    @staticmethod
    def section(text: str):
        print(f"[###] {text}", flush=True)


    @staticmethod
    def warning(text: str):
        print(f"[\033[33m{'!!!'}\033[0m] {text}", flush=True)


    @staticmethod
    def fatal(text: str):
        print(f"[\033[31m{'ERR'}\033[0m] {text}", flush=True)
        sys.exit(1)





def is_html(response: requests.Response) -> bool:
    return (
        "Content-Type" in response.headers
        and "text/html" in response.headers["Content-Type"]
    )



def is_safe_path(path: str) -> bool:
    """ Prevent directory traversal attacks """
    if path.startswith("/"):
        return False

    safe_path = os.path.expanduser("~")
    return (
        os.path.commonpath(
            (os.path.realpath(os.path.join(safe_path, path)), safe_path)
        )
        == safe_path
    )



def get_indexed_files(response: requests.Response) -> list:
    html  = bs4.BeautifulSoup(response.text, "html.parser")
    files = []

    for link in html.find_all("a"):
        url = urllib.parse.urlparse(link.get("href"))

        if (
            url.path
            and is_safe_path(url.path)
            and not url.scheme
            and not url.netloc
        ):
            files.append(url.path)

    return files




def verify_response(response: requests.Response) -> tuple[bool, bool, str]:
    Display.response(response)

    if response.status_code >= 400:
        return False, False, None
    
    elif response.status_code >= 300 and "Location" in response.headers:
        return False, True, f"Moved to {response.headers['Location']}. Code {response.status_code}"
    
    elif (
        "Content-Length" in response.headers
        and response.headers["Content-Length"] == 0
    ):
        return False, True, "Responded with a zero-length body"
    
    elif is_html(response):
        return False, True, f"{response.url} responded with a HTML"
    
    else:
        return True, False, None




def create_intermediate_dirs(path: str):
    dirname, basename = os.path.split(path)

    if dirname and not os.path.exists(dirname):
        try:
            os.makedirs(dirname)
        except FileExistsError:
            pass  # race condition




def get_referenced_sha1(obj_file):
    """ Return all the referenced SHA1 in the given object file """
    objs = []

    if isinstance(obj_file, dulwich.objects.Commit):
        objs.append(obj_file.tree.decode())

        for parent in obj_file.parents:
            objs.append(parent.decode())

    elif isinstance(obj_file, dulwich.objects.Tree):
        for item in obj_file.iteritems():
            objs.append(item.sha.decode())
    
    elif isinstance(obj_file, dulwich.objects.Blob):
        pass
    elif isinstance(obj_file, dulwich.objects.Tag):
        pass
    else:
        Display.fatal(f"Unexpected object type: {obj_file}")

    return objs





class Worker(multiprocessing.Process):

    def __init__(
            self, 
            pending_tasks : multiprocessing.Queue, 
            tasks_done    : multiprocessing.Queue,
            args          : Arguments
        ):
        super().__init__()
        self.daemon        : bool                  = True
        self.pending_tasks : multiprocessing.Queue = pending_tasks
        self.tasks_done    : multiprocessing.Queue = tasks_done
        self.args          : Arguments             = args



    def run(self):
        self.init(self.args)

        # fetch and do tasks
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

            assert isinstance(
                result, list
            ), "do_task() should return a list of tasks"

            self.tasks_done.put(result)


    def init(self, args: Arguments):
        raise NotImplementedError


    def do_task(self, task, args: Arguments) -> list:
        raise NotImplementedError





class DownloadWorker(Worker):

    def init(self, args: Arguments):
        if hasattr(self, '_session'):
            return
        
        self._delay   : float            = args.delay 
        self._session : requests.Session = requests.Session()         
        
        self._session.verify = False
        self._configure_session(args)
        
    

    def _configure_session(self, args: Arguments):
        self._session.headers.clear()
        self._session.headers.update(args.http_headers)
        self._session.headers.pop("Accept-Encoding", None)

        if not args.client_cert_p12:
            self._session.mount(args.url, requests.adapters.HTTPAdapter(max_retries=args.retry))
            return
        
        self._session.mount(
            args.url, Pkcs12Adapter(
                pkcs12_filename=args.client_cert_p12, 
                pkcs12_password=args.client_cert_p12_password
            )
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

            # write file
            with open(abspath, "wb") as f:
                for chunk in response.iter_content(4096):
                    f.write(chunk)

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
                assert is_html(response)

                return [
                    filepath + filename
                    for filename in get_indexed_files(response)
                ]
            
            # file
            valid, display, error_msg = verify_response(response)

            if not valid:
                if display:
                    Display.warning(f"Invalid response from {response.url}: {error_msg}")
                return []
            
            abspath = os.path.abspath(os.path.join(args.directory, filepath))
            create_intermediate_dirs(abspath)
            # write file
            
            with open(abspath, "wb") as f:
                for chunk in response.iter_content(4096):
                    f.write(chunk)
            
            return []





class FindRefsWorker(DownloadWorker):

    def do_task(self, filepath: str, args: Arguments) -> list:
        response = self._request(f"{args.url}/{filepath}", allow_redirects=False, timeout=args.timeout)

        valid, display, error_msg = verify_response(response)

        if not valid:
            if display:
                Display.warning(f"Invalid response from {response.url}: {error_msg}")
            return []

        abspath = os.path.abspath(os.path.join(args.directory, filepath))
        create_intermediate_dirs(abspath)

        # write file
        with open(abspath, "w") as f:
            f.write(response.text)

        # find refs
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
            print(f"[---] Already downloaded {args.url}/{filepath}",flush=True)
        else:
            if not self._get_obj(filepath, args):
                return []

        try:
            abspath = os.path.abspath(os.path.join(args.directory, filepath))        
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
        
        # write file
        with open(abspath, "wb") as f:
            f.write(response.content)
        
        return True




if __name__ == "__main__":
    try:
        git_looter = GitBleed()
        git_looter.execute()
        sys.exit(0)
    except KeyboardInterrupt : pass
    except Exception as e    : Display.fatal(f'{e}')
