# NTSB aviation accident database (SQLite)

Coverage: NTSB investigations of events from {since_year} onward. Latest event date in this load: {max_ev_date}.
Includes accidents (ACC) and incidents (INC), U.S. and foreign (foreign events often have sparse fields).

## Keys and joins
- `ev_id` identifies an event. Every table except the lookups has it.
- Aircraft-level tables (`aircraft`, `narratives`, `findings`, `events_sequence`) are keyed by (`ev_id`, `aircraft_key`). A mid-air collision has 2+ aircraft rows for one event.
- Joining `events` to any aircraft-level table multiplies rows. To count events, use `COUNT(DISTINCT events.ev_id)`.

## events (one row per event)
- `ev_id` TEXT — internal key.
- `ntsb_no` TEXT — the NTSB report number (e.g. `WPR15FA072`). This is the citation for any claim about a specific event. Always select it when returning event-level rows.
- `ev_type` TEXT — `ACC` accident, `INC` incident.
- `ev_date` TEXT `YYYY-MM-DD 00:00:00`; `ev_year` INTEGER; `ev_month` INTEGER; `ev_time` INTEGER local time as HHMM.
- `ev_city`, `ev_state` (2-letter US state), `ev_country` (`USA` or 2-letter code), `dec_latitude`, `dec_longitude` REAL.
- `ev_nr_apt_id` TEXT — nearest airport identifier, usually the FAA ID (`DEN`) but sometimes ICAO (`KDEN`) or `NONE`. Match both forms: `ev_nr_apt_id IN ('DEN','KDEN')`. `apt_name` (free text); `apt_dist` REAL miles.
- `ev_highest_injury` — `FATL` fatal, `SERS` serious, `MINR` minor, `NONE`; can be NULL.
- `inj_tot_f`, `inj_tot_s`, `inj_tot_m`, `inj_tot_n` INTEGER — total fatal / serious / minor / uninjured (NULL means none recorded, treat as 0 with `COALESCE`).
- `wx_cond_basic` — `VMC`, `IMC`, `UNK`. Case varies (`Unk`), so compare with `UPPER(wx_cond_basic)`. NULL for most foreign events.
- `light_cond` — `DAYL`, `DAWN`, `DUSK`, `NITE`, `NDRK` (night/dark), `NBRT` (night/bright), `NR`.
- Weather observation: `wind_dir_deg`, `wind_vel_kts`, `gust_kts`, `vis_sm` (statute miles), `sky_ceil_ht` (ft AGL), `wx_temp`, `wx_dew_pt` (°C), `altimeter`, `metar` TEXT (raw METAR if recorded).

## aircraft (one row per aircraft per event)
- `ev_id`, `aircraft_key`, `ntsb_no`.
- `regis_no` TEXT — registration / tail number (U.S. N-numbers stored with the `N`, e.g. `N12345`).
- `acft_make`, `acft_model`, `acft_series` TEXT — free text, inconsistent. Makes appear as `CESSNA`, `Cessna`, `Cessna Aircraft Co`, `TEXTRON AVIATION Cessna` etc. Always match with `UPPER(acft_make) LIKE '%CESSNA%'`. Models vary too (`172`, `172S`, `PA28`, `PA-28-181`): use `LIKE` prefixes and state the assumption.
- `acft_category` — `AIR` airplane, `HELI` helicopter, `GLI` glider, `BALL` balloon, `GYRO`, `WSFT` weight-shift, `PPAR` powered parachute, ...
- `damage` — `DEST` destroyed, `SUBS` substantial, `MINR` minor, `NONE`, `UNK`.
- `far_part` — operating rule: `091` general aviation, `121` air carrier, `135` air taxi/commuter, `137` agricultural, `141` pilot school, `129` foreign carrier, `NUSC`/`NUSN` non-U.S. commercial/non-commercial, `PUBU` public use, `UNK`.
- `type_fly` — purpose of flight, e.g. `PERS` personal, `INST` instructional, `BUS` business, `AAPL` aerial application, `POSI` positioning; decode others via `data_dictionary`.
- `num_eng` INTEGER, `homebuilt` (`Y`/`N`), `oper_name` TEXT (operator, e.g. airline), `dprt_apt_id`, `dest_apt_id`.
- Do NOT use `phase_flt_spec` (always NULL since 2015; phase lives in `events_sequence`).

## narratives (one row per aircraft per event; ~16% of events have none yet)
- `narr_accp` TEXT — full factual narrative (long; avg ~4,000 chars).
- `narr_accf` TEXT — shorter summary narrative (avg ~1,300 chars).
- `narr_cause` TEXT — the probable cause statement.
- Only select narrative text when the question needs it, and only for a few events (use `LIMIT`). For keyword search use `LIKE '%term%'` on `narr_accp`.

## findings (many per aircraft; ~28% of events have none, e.g. open or foreign investigations)
- `finding_description` TEXT — hierarchical, dash-separated: `Category-Subcategory-Section-Subsection-Modifier`, sometimes with a trailing ` - C`.
  e.g. `Personnel issues-Task performance-Use of equip/info-Aircraft control-Pilot`, `Aircraft-Aircraft oper/perf/capability-Performance/control parameters-Directional control-Not attained/maintained`, `Environmental issues-Conditions/weather/phenomena-...`.
  Top-level categories: `Aircraft`, `Personnel issues`, `Environmental issues`, `Organizational issues`, `Not determined`. Match with `LIKE`.
- `cause_factor` — `C` = cited as a cause, `F` = contributing factor; NULL/empty = neither.
- `finding_code` TEXT — numeric code for the same hierarchy.

## events_sequence (ordered occurrences per aircraft)
- `occurrence_no` INTEGER order; `phase_no` TEXT phase-of-flight code (join `phase_of_flight`).
- `occurrence_description` TEXT — `<phase> <occurrence>`, e.g. `Landing-landing roll Runway excursion`, `Enroute VFR encounter with IMC`, `Takeoff Loss of control in flight`.
- `defining_ev` INTEGER — 1 marks the event's defining occurrence (use this for "what kind of accident was it").

## phase_of_flight (lookup)
- `phase_no` TEXT, `phase_name` TEXT. Hundreds group sub-phases: `300` Takeoff, `350` Initial climb, `400`–`405` Enroute, `450`–`453` Maneuvering, `500`–`509` Approach, `550`–`553` Landing, `600` Emergency descent, `650` Uncontrolled descent.
- For a whole phase family use ranges, e.g. landing = `phase_no BETWEEN '550' AND '553'`.

## data_dictionary (code lookups)
- `table_name`, `column_name` (lowercase, matching this database), `code_iaids` (the code), `meaning`, `short_desc`.
- Use it to decode any coded column, e.g. `SELECT code_iaids, meaning FROM data_dictionary WHERE table_name='aircraft' AND column_name='type_fly'`.
