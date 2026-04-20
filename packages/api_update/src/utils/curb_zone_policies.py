import uuid
import pandas as pd


def add_curb_zone_policy(
        curb_zone_policies: pd.DataFrame,
        curb_zone_id: uuid.UUID,
        curb_policy_id: uuid.UUID,
) -> pd.DataFrame:

    new_row_gdf = pd.DataFrame([
        {
            "curb_zone_id": curb_zone_id,
            "curb_policy_id": curb_policy_id
        }
    ])
    curb_zone_policies = pd.concat([curb_zone_policies, new_row_gdf], ignore_index=True)

    return curb_zone_policies


def remove_curb_zone_policy(
        curb_zone_policies: pd.DataFrame,
        curb_zone_id: uuid.UUID,
        curb_policy_id: uuid.UUID,
) -> pd.DataFrame:

    mask1 = curb_zone_policies['curb_zone_id'] == curb_zone_id
    mask2 = curb_zone_policies['curb_policy_id'] == curb_policy_id
    mask = mask1 & mask2
    curb_zone_policies = curb_zone_policies.loc[~mask].reset_index(drop=True)

    return curb_zone_policies

