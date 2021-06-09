import os
import urllib.request
import requests
import pathlib
import sys
import glob
import json
import shutil
from git import Repo
from git.remote import RemoteProgress
from tqdm import tqdm
from zipfile import ZipFile
from typing import Dict, List


class CloneProgress(RemoteProgress):
    def __init__(self) -> None:
        super().__init__()
        self.pbar = tqdm()

    def update(self, op_code: int, cur_count: int, max_count: int = None, message: str = '') -> None:
        self.pbar.total = max_count
        self.pbar.n = cur_count
        self.pbar.refresh()


class DownloadProgressBar(tqdm):
    def update_to(self, b: int = 1, bsize: int = 1, tsize: int = None) -> None:
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)


class ModelHub:
    def __init__(self,
                 models: Dict[str, Dict[str, str]] = None,
                 local_storage: str = None,
                 remote_storage: str = None,
                 postfix: str = "./modelhub",
                 ) -> None:
        if models is None:
            models = {}
        if local_storage is None:
            local_storage = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                postfix
            )
        self.models = models
        self.local_storage = local_storage
        self.remote_storage = remote_storage

    def ls(self, subdir: str = "./") -> List[str]:
        dirs_list = []
        for model_name in self.models:
            info = self.models[model_name]
            path = os.path.join(self.local_storage,
                                subdir,
                                info["application"],
                                model_name)
            if os.path.exists(path):
                dir_list = os.listdir(path)
                dirs_list.extend(dir_list)
        return dirs_list

    def rm(self, subdir: str = "./") -> None:
        models_dir = os.path.join(self.local_storage, subdir)
        shutil.rmtree(models_dir, ignore_errors=True)

    def ls_models_local(self) -> List[str]:
        return self.ls("./models")

    def ls_datasets_local(self) -> List[str]:
        return self.ls("./datasets")

    def ls_repos_local(self) -> List[str]:
        return self.ls("./repos")

    def rm_models_local(self) -> None:
        self.rm("./models")

    def rm_datasets_local(self) -> None:
        self.rm("./datasets")

    def rm_repos_local(self) -> None:
        self.rm("./repos")

    @staticmethod
    def download(url, output_path):
        print("Downloaded model path:", output_path)
        with DownloadProgressBar(unit='B',
                                 unit_scale=True,
                                 miniters=1,
                                 desc=url.split('/')[-1]) as t:
            urllib.request.urlretrieve(url,
                                       filename=output_path,
                                       reporthook=t.update_to)

    def download_model_by_name(self, model_name: str) -> Dict[str, str]:
        info = self.models[model_name]
        info["path"] = os.path.join(self.local_storage,
                                    "./models",
                                    info["application"],
                                    model_name,
                                    os.path.basename(info["url"]))

        p = pathlib.Path(os.path.dirname(info["path"]))
        p.mkdir(parents=True, exist_ok=True)

        output_path = info['path']
        _, file_extension = os.path.splitext(info['path'])
        if file_extension == '.zip':
            archive_name = os.path.basename(info["path"])
            _, archive_dir_name = os.path.splitext(archive_name)
            archive_dir_path = os.path.join(os.path.dirname(info['path']), archive_dir_name)
            info['path'] = archive_dir_path

        if os.path.exists(info["path"]):
            return info

        self.download(info["url"], info["path"])
        if file_extension == '.zip':
            with ZipFile(output_path, 'r') as zipObj:
                dir_to_extract = os.path.join(os.path.dirname(info['path']))
                zipObj.extractall(dir_to_extract)
                os.remove(output_path)
        return info

    def download_dataset_for_model(self, model_name):
        info = self.models[model_name]
        info["dataset_path"] = os.path.join(self.local_storage,
                                            "./dataset",
                                            info["application"],
                                            model_name,
                                            os.path.basename(info["dataset"]))
        p = pathlib.Path(os.path.dirname(info["dataset_path"]))
        p.mkdir(parents=True, exist_ok=True)

        dataset_path = info['dataset_path']
        _, file_extension = os.path.splitext(info['dataset_path'])
        if file_extension != '.zip':
            raise Exception("Not supported file extension!")

        archive_name = os.path.basename(info["dataset_path"])
        _, archive_dir_name = os.path.splitext(archive_name)
        archive_dir_path = os.path.join(os.path.dirname(info['dataset_path']), archive_dir_name)
        info['dataset_path'] = archive_dir_path

        self.download(info["dataset"], info["dataset_path"])
        with ZipFile(dataset_path, 'r') as zipObj:
            dir_to_extract = os.path.join(os.path.dirname(info['path']))
            zipObj.extractall(dir_to_extract)
            os.remove(dataset_path)
        return info

    def download_repo_for_model(self, model_name: str) -> None:
        info = self.models[model_name]
        info["repo_path"] = os.path.join(self.local_storage,
                                         "./repos",
                                         info["application"],
                                         model_name,
                                         os.path.basename(info["repo"]))
        if not os.path.exists(info["repo_path"]):
            print("git clone", info["repo"])
            Repo.clone_from(info["repo"],
                            info["repo_path"],
                            progress=CloneProgress())
        sys.path.append(info["repo_path"])

    def save_remote_file(self, update_file: str, filename: str) -> None:
        url = os.path.join(self.remote_storage, update_file)
        request = requests.put(url, data=open(filename, 'rb').read(), headers={})
        return json.loads(request.content)

    def rm_remote(self, dir_for_remove):
        url = os.path.join(self.remote_storage, dir_for_remove)
        res = requests.request('DELETE', url)
        return res

    def mkdir_remote(self, new_dir):
        if new_dir[-1] != "/":
            new_dir = f"{new_dir}/"
        url = os.path.join(self.remote_storage, new_dir)
        res = requests.request('MKCOL', url)
        return res

    def store_remote_file(self, local_dir, server_dir, filename):
        upload_from = os.path.join(local_dir, filename)
        upload_to = os.path.join(server_dir, filename)
        return self.save_remote_file(upload_to, upload_from)

    def store_remote(self, local_dir: str, server_dir: str = "./", remove_source: bool = False):
        server_dir_path = ""
        for server_d in server_dir.split("/"):
            server_dir_path = os.path.join(server_dir_path, server_d)
            print(server_dir_path)
            self.mkdir_remote(server_dir_path)

        for file in glob.glob(os.path.join(local_dir, "*")):
            print("Store remote", file)
            self.store_remote_file(local_dir, server_dir, os.path.basename(file))

        if remove_source:
            shutil.rmtree(local_dir)