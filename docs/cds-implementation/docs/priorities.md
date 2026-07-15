---
icon: lucide/arrow-down-up
---

# Policy Prioritization

The examples shown above are useful in understanding the order in which 
policies must be prioritized to achieve correct representation of parking 
regulations. To allow for potential expansion and refinement, we have 
categorized policies into blocks of 10 to leave some space for expansion
and adjustment.


| Priority | Category | Description |
|----------|----------|-------------|
| 1-9 | **Blanket Prohibitions** | All blanket prohibitions of activities, including `no stopping`, `no loading`, and `no parking` prioritized as `1`, `2`, and `3`, respectively. Blanket prohibitions apply to all user classes, purposes, and `time_spans`. |
| 10-19 | **Temporary Allowances** | Allowances with a start and stop date. |
| 20-29 | **Temporary Prohibitions** | Prohibitions with a start and stop date. |
| 30-39 | **Time-specific General Prohibitions** | Prohibitions that apply to all users such as Snow Emergencies, or days and times when parking is prohibited to allow street cleaning. <br><br>Block 30-34 is used for designated periods such as Snow Emergency; block 35-39 is used for other `time_spans`. |
| 40-49 | **User- and time-specific allowances** | Target one or more specific `user_class` or `purpose` and are also only in effect for specified `time_spans`. |
| 50-59 | **User- and time-specific prohibitions** | Target one or more specific `user_class` or `purpose` and are also only in effect for specified `time_spans`. |
| 60-69 | **User-specific allowances** | Target one or more `user_class` or `purpose` but are not limited to specific `time_spans`. |
| 70-79 | **User-specific prohibitions** | Target one or more `user_class` or `purpose` but are not limited to specific `time_spans`. |
| 80-89 | **Time-specific General Allowances** | In effect only for specific `time_spans`, but do not target a specific `user_class` or `purpose`. |
| 90-99 | **Blanket Allowances** | Apply to all users during all `time_spans`. The catchall unrestricted parking allowance that allows parking for all vehicles and `time_spans` uses a priority value of `99`. |


!!! warning "Temporary Parking"
    Temporary parking regulations were not a focus for this study, so prioritization 
    has not been fully explored.
