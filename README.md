# Ducati Blend Calculator

A Python application for calculating optimal blends based on batch data, using exact MILP optimisation and a Tkinter GUI.

## Features
- CSV viewer and editor with inline cell editing  
- Excel → CSV converter  
- Target‑based blend calculation using PuLP + CBC solver  
- Support for leaching limits and asymmetric weight tolerances  
- Automatic multi‑blend computation  
- Interactive plots (matplotlib)  
- Summary and detailed per‑blend tabs  
- Export results to JSON or CSV  

## Requirements
- Python 3.8+
- Packages:
  - `pulp`
  - `ttkbootstrap`
  - `matplotlib`
  - `pandas` (if used)
  - any others your project imports

Install all dependencies:


pip install -r requirements.txt


## Running the GUI


python GUI_ST_batches_call_calc_fixed_v11a.py


## Running the solver directly


python target_based_solver.py --input input.json


## Project Structure


/project
├── GUI_ST_batches_call_calc_fixed_v11a.py
├── target_based_solver.py
├── results_views.py
├── blend_runner.py
├── plot_helpers.py
└── ...
```

## License
To be added.
