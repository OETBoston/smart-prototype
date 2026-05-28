---
icon: lucide/user-round-pen
---

# CDS Adaptations and Implementation Notes

Some elements of the CDS API spec require a bit of interpretation, or some 
explicit decisions that may vary from implementation to implementation. 
Such decisions are documented here.

## Catchall Policy

The Boston CDS implementation describes allowable activities (e.g., parking)
in a curb zone for various user classes (e.g., passenger cars or commercial vehicles).
This is accomplished through automated
interpretation of sign images and conversion of these images to one or more
**policy** objects that represent rules on a sign.

To fully define activities on each curb, we use a pair of catchall policies:

1. A no stopping anytime policy, applied in cases where a blockface has been
marked through other means such as lane marking analysis to be a travel lane.
2. An unrestricted parking policy, applied in all cases but at a lower priority 
than the no stopping policy. 

These policies are prioritized in a manner consistent with the [prioritization 
approach](priorities.md). Of note, the unrestricted parking policy is assigned a specific 
priority value of 99.

## Explicit Exclusion
Applications relying on CDS feeds must be capable of parsing, at a given time, who is 
allowed to do what within a Curb Zone. To avoid ambiguous interpretations of which 
Policies or Rules apply to a given user class, the proposed Boston implementation aims 
to be as explicit as possible about which activities are allowed and prohibited for 
different user classes.

Usually, this can be sufficiently accomplished by preferring negative activities to
limit parking to specific users -- e.g. "No Parking Except EVs" is better than "EV Parking",
since the latter could be understood by some applications as being silent about the remaining user classes. In that case, a lower priority Policy (including the underlying "Unrestricted" Policy) could be identified as containing the applicable regulations for other users.

Multiple rules may required in certain situations for maximum clarity and composability 
of Policies at different priorities. In situations where Zone is reserved for a specific
user class, but subject to specific conditions (such as a rate or time limit), two rules 
are generally required:

1. A rule **prohibiting** an activity for all users _except_ the specified user class.
2. A rule **allowing** that activity for that specific class, along with the conditions
(CDS is clear that meter rates cannot be attached to negative policies, and "No Parking
2 Hours Max" makes little sense).

For example, a policy that allows 30-minute commercial vehicle parking only between 
6:00 am and 10:00 am (Monday-Friday), and allows unrestricted parking at other times might be
represented by the example below:

```json
[
  {
    "name": "Policy 1 - Limited commercial vehicle loading",
    "priority": 1,
    "rules": [
      {"activity": "no loading", "user_classes_except": "commercial_vehicles"},
      {
        "activity": "loading",
        "max_stay": 30,
        "max_stay_unit": "minute",
        "user_classes": ["commercial_vehicle"]
      }
    ],
    "time_spans": [
      {
        "time_of_day_start": "06:00",
        "time_of_day_end": "10:00",
        "days_of_week": ["mon", "tue", "wed", "thu", "fri"]
      }
    ]
  },
  {
    "name": "Unrestricted parking",
    "priority": 99,
    "rules": [{"activity": "parking"}],
    "time_spans": [
      {
        "time_of_day_start": "00:00",
        "time_of_day_end": "00:00",
        "days_of_week": ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
      }
    ]
  }
]
```

The remainder of this document relies on these assumptions.

## Loading Activity

The list of activities includes both `loading` and `unloading`, and defines these activities 
as loading or unloading of goods, respectively. The distinction is unnecessary given parking 
regulations in Boston, as is the restriction of `loading` to apply only to goods. Therefore, 
we have modified `loading` to be defined as follows:

> loading and/or unloading of goods or people; implies that stopping is also permitted.

In addition, the `unloading` and `no unloading` activities are not used, as unloading goods
and passengers is generally permitted wherever `loading` is allowed.

## Enumerated Values

CDS includes well known values for User Classes and for Purposes. Our implementation
is deliberately limited to the values described below.

### User Classes

CDS defines `user_class` field as using the **AND** operator. We've created
a set of values different from the well known values included in the CDS
specification that is more applicable to Boston parking regulations
encountered in this process. This list includes:

- Vehicle Types
    - bicycle
    - bus
    - car
    - motorcycle
    - truck
- Vehicle Properties
    - accessible
    - electric

- Additional Values (not well known values listed in CDS)
    - commercial_vehicle
    - resident_permit
    - rideshare
    - valet

It is assumed that vehicles classified as `moped` or `scooter` are subject to same rules
as the `motorcycle` class, and so reducing these to a single class results in expressive,
consice CDS. Otherwise, separate rules would be required for each of the three classes.

HP/DV permit holders are covered by the `accessible` class.

Additional `user_class` values may be added as they are encountered in the
dataset.

### Purposes

This project is minimizing the `purpose` field, which is specified as
using an **OR** operator. The values of purpose encountered so far include:

- emergency_use
- pickup_dropoff (not a CDS well known value, but helps to distinguish PUDO areas)

Examples of use cases where `purpose` is important include:

- School zone pick-up and drop-off only, usually time-limited.
- Zones reserved for emergency ambulance use.

Hydrant areas are also tagged with the purpose emergency use to help distinguish them.

Purpose is not used to describe allowable activities that are the reason for a
no-parking regulation, such as street sweeping or temporary construction access.

Additional `purpose` values may be added as they are encountered in the
dataset.

# Timespans
Timespans describe which days and times a Policy is in effect. If a Policy applies 24/7,
CDS permits omitting this field.

The Boston implementation always explicitly includes the following fields, which are the
most commonly used time-specific fields on parking signage.
- time_of_day_start
- time_of_day_end
- days of week

A policy applying all day uses the time span (midnight to midnight):

```json
{
  "time_of_day_start": "00:00",
  "time_of_day_end": "00:00",
  "days_of_week": ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
}
```
While more verbose, this aims to increase the consistency of outputs within an AI-driven 
inventory framework.