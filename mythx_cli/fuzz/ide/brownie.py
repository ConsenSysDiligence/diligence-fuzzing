import logging
from pathlib import Path
from typing import List

from mythx_cli.fuzz.exceptions import BuildArtifactsError
from mythx_cli.fuzz.ide.generic import IDEArtifacts, JobBuilder

from ...util import files_by_directory, sol_files_by_directory

LOGGER = logging.getLogger("mythx-cli")


class BrownieArtifacts(IDEArtifacts):
    def __init__(self, build_dir=None, targets=None, map_to_original_source=False):
        self._include = []
        if targets:
            include = []
            for target in targets:
                if not map_to_original_source:
                    LOGGER.debug(f"Mapping instrumented code")
                    include.extend(files_by_directory(target, ".sol"))
                else:
                    # We replace .sol with .sol.original in case the target is a file and not a directory
                    target = target.replace(".sol", ".sol.original")
                    LOGGER.debug(f"Mapping original code, {target}")
                    include.extend(files_by_directory(target, ".sol.original"))
            self._include = include

        self._build_dir = build_dir or Path("./build/contracts")
        build_files_by_source_file = self._get_build_artifacts(self._build_dir)

        self._contracts, self._sources = self.fetch_data(build_files_by_source_file)

    @property
    def contracts(self):
        return self._contracts

    @property
    def sources(self):
        return self._sources

    def fetch_data(self, build_files_by_source_file):
        result_contracts = {}
        result_sources = {}
        for source_file, contracts in build_files_by_source_file.items():
            if source_file not in self._include:
                continue
            result_contracts[source_file] = []
            for contract in contracts:
                # We get the build items from brownie and rename them into the properties used by the FaaS
                try:
                    result_contracts[source_file] += [
                        {
                            "sourcePaths": contract["allSourcePaths"],
                            "deployedSourceMap": contract["deployedSourceMap"],
                            "deployedBytecode": contract["deployedBytecode"],
                            "sourceMap": contract["sourceMap"],
                            "bytecode": contract["bytecode"],
                            "contractName": contract["contractName"],
                            "mainSourceFile": contract["sourcePath"],
                        }
                    ]
                except KeyError as e:
                    raise BuildArtifactsError(
                        f"Build artifact did not contain expected key. Contract: {contract}: \n{e}"
                    )

                for file_index, source_file_dep in contract["allSourcePaths"].items():
                    if source_file_dep in result_sources.keys():
                        continue

                    if source_file_dep not in build_files_by_source_file:
                        LOGGER.debug(f"{source_file} not found.")
                        continue

                    # We can select any dict on the build_files_by_source_file[source_file] array
                    # because the .source and .ast values will be the same in all.
                    target_file = build_files_by_source_file[source_file_dep][0]
                    result_sources[source_file_dep] = {
                        "fileIndex": file_index,
                        "source": target_file["source"],
                        "ast": target_file["ast"],
                    }
        return result_contracts, result_sources


class BrownieJob:
    def __init__(
        self, target: List[str], build_dir: Path, map_to_original_source: bool
    ):
        artifacts = BrownieArtifacts(
            build_dir, targets=target, map_to_original_source=map_to_original_source
        )
        self._jb = JobBuilder(artifacts)
        self.payload = None

    def generate_payload(self):
        self.payload = self._jb.payload()
