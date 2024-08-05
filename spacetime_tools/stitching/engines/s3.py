import os
import pandas as pd
import logging
import spacetime_tools.stitching.helpers as helpers

logger = logging.getLogger(__name__)


class S3:
    def __init__(self, options) -> None:
        no_sign_flag = ""
        request_payer_flag = ""
        profile_flag = ""
        json_flag = "--json"

        self.options = options

        if ("no_sign_request" in self.options) and (self.options["no_sign_request"]):
            no_sign_flag = "--no-sign-request"

        if ("request_payer" in self.options) and (self.options["request_payer"]):
            request_payer_flag = f"--request-payer {self.options['request_payer']}"

        if "profile" in self.options:
            profile_flag = f"--profile {self.options['profile']}"

        self.base_cmd = (
            f"s5cmd {no_sign_flag} {request_payer_flag} {profile_flag} {json_flag}"
        )

    def optimize_pattern_search(self, patterns):
        """
        Reduces the number of patterns to search by finding the first wildcard in every pattern.
        Once we have patterns till first wild-card we simply remove the duplicates and return
        """
        first_wildcard_pats = []
        for i in range(len(patterns)):
            idx = patterns[i].find("*")
            first_wildcard_pats.append(patterns[i][:idx+1])
        return list(set(first_wildcard_pats))

    def create_inventory(self, patterns, tmp_base_dir):
        # TODO: Add optimization to search till common first wildcard and filter them later
        # This is done because sometimes space dimension is before time and s5cmd lists all files till first wildcard and then filters them in memory
        ls_cmds_fp = f"{tmp_base_dir}/ls_commands.txt"
        inventory_file_path = f"{tmp_base_dir}/s3-inventory.csv"
        df = pd.DataFrame(patterns, columns=["path"])
        
        # go-lib expects paths in unix style
        df["path"] = df["path"].str.replace("s3://", "/")

        df.to_csv(ls_cmds_fp, index=False, header=False)

        ls_cmd = f"stitching/shared_libs/builds/go-lib {ls_cmds_fp} {inventory_file_path}"
        os.system(ls_cmd)

        df = pd.read_csv(inventory_file_path, names=["key"])

        # Fixing output from go-lib
        df["key"] = "s3://" + df["key"].str[1:]

        # Adding gdal_path
        df["gdal_path"] = df["key"].str.replace("s3://", "/vsis3/")
        df["engine_path"] = df["key"]

        return df[["engine_path", "gdal_path"]]

    def sync_inventory(self, df, tmp_base_dir):
        # Deleting /raw dir where data will be synced
        base_path = f"{tmp_base_dir}/raw"
        helpers.delete_dir(f"{base_path}/")
        local_path = f"{base_path}/" + df["engine_path"].map(
            lambda x: x.replace("s3://", "")
        )
        cmds = "cp" + " " + df["engine_path"].map(str) + " " + local_path
        cmds_fp = f"{tmp_base_dir}/sync_commands.txt"

        cmds.to_csv(cmds_fp, header=False, index=False)
        s5_cmd = f"{self.base_cmd} run {cmds_fp}"

        os.system(s5_cmd)

        df["local_path"] = local_path
        return df
