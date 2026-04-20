# Direction of Flow in Curb Dataset
The curb dataset (also called the blockface dataset) results from the curb geometry creation process using the [MassDOT Road Inventory Dataset](https://geo-massdot.opendata.arcgis.com/datasets/MassDOT::road-inventory-2024/explore) to generate curb lines via street centerline buffers. It is formatted for loading curb blockface geometries into the `curb_blockfaces` table in a PostgreSQL database.

## Direction of flow

As defined in the [staging database structure](https://github.com/OETBoston/smart-prototype/blob/main/docs/staging_database.md), the `curb_blockfaces` table includes a `direction_of_flow` field indicating traffic flow direction (`forward` or `reverse`) relative to the digitized curb line direction. This value derives directly from the Road Inventory dataset fields without additional data sources.

## Fields in the Road Inventory dataset

* `Operation`: Specifies one-way vs. two-way roads.
  * `1`: One-way traffic  
  * `2`: Two-way traffic  
  * `3`: One-way traffic – dual carriageway  

* `Oneway`: Describes the travel direction on one-way roads relative to road digitization.
  * `FT`: From-to (with line digitization direction)  
  * `TF`: To-from (against line digitization direction)  

* `side`: Specifies which side of the street centerline the curb is on, relative to the digitized direction.
  * `right`: The curb is on the right side of the street centerline.  
  * `left`: The curb is on the left side of the street centerline.  

## Direction assignment rules
The `"direction"` field is assigned by these conditions:

| Rule | `operation` | `oneway` | `side`  | Resulting `direction_of_flow` |
|:----:|:-----------:|:--------:|:-------:|:-----------------------------:|
|  1   | `1` or `3`  |   `FT`   |  _Any_  |           `forward`           |
|  2   | `1` or `3`  |   `TF`   |  _Any_  |           `reverse`           |
|  3   |     `2`     |  _Any_   | `right` |           `forward`           |
|  4   |     `2`     |  _Any_   | `left`  |           `reverse`           |
|  5   |    _Any_    |  _Any_   |  _Any_  |            `None`             |

## Notes
* `oneway` applies only to `operation` values `1` and `3`.
* `side` applies only to `operation` value `2`.
* `None` means no defined rule applies; no such cases observed.
* About 50 roads (~0.2%) lack values in the `operation` field. 
Manual inspection shows these segments are tiny, mostly oneway with traffic aligned to line digitization. They are treated as oneway with `FT,` yielding `forward` direction of flow.

