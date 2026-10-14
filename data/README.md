# Training data

`heat_risk_training.csv` contains 315,648 hourly weather observations from 2020-01-01 through 2025-12-31 for Mumbai, Delhi, Phoenix, Kuwait City, Miami, and Oslo. The historical temperature and relative-humidity observations were downloaded from the Open-Meteo Archive API and are provided under CC BY 4.0.

`risk_level` and `risk_code` are generated labels from this repository's NOAA heat-index calculation and threshold table. They are not measured health outcomes or independent expert annotations. `heat_index_c` is included for inspection but is not used as a model feature.