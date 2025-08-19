import pandas as pd
import numpy as np


def load_and_clean_data(filepath=r"redcap_baseline_complete.csv"):
    """
    Loads the raw REDCap facility data, performs all necessary cleaning steps,
    and returns a clean DataFrame ready for analysis.

    Args:
        filepath (str): The full path to the CSV data file.

    Returns:
        pd.DataFrame: A cleaned and prepared pandas DataFrame.
    """
    print("--- Starting Data Loading and Cleaning ---")
    
    try:
        df = pd.read_csv(filepath)
    except FileNotFoundError:
        print(f"Error: Data file not found at {filepath}")
        return None

    # --- Initial Cleaning ---
    if 'Unnamed: 0' in df.columns:
        df.drop(columns=['Unnamed: 0'], inplace=True)
    
    # --- Data Type Correction for Staff Counts ---
    staff_col_keywords = ['employed', '_start', '_end', '_hiv', '_ncd', '_trained', '_left']
    cols_to_convert = [
        col for col in df.columns 
        if any(keyword in col for keyword in staff_col_keywords) and df[col].dtype == 'float64'
    ]
    df[cols_to_convert] = df[cols_to_convert].fillna(0).astype(int)
    print(f"Corrected data types for {len(cols_to_convert)} staffing columns.")

    # --- Convert Placeholders (e.g., 9999) to NaN ---
    placeholders_to_replace = [9999.0, 99999.0, 999999.0, 9999999.0]
    numeric_cols = df.select_dtypes(include=np.number).columns
    for col in numeric_cols:
        df[col] = df[col].replace(placeholders_to_replace, np.nan)
    print(f"Scanned for and replaced placeholders in numeric columns.")

    # --- Coerce Patient Count Columns to Numeric ---
    patient_count_prefixes = ['outpatient_', 'hiv_', 'diabetes_', 'htn_', 'dm_htn_', 'hiv_dm_', 'hiv_htn_', 'hiv_htn_dm_']
    all_patient_cols = [col for col in df.columns if any(col.startswith(p) for p in patient_count_prefixes)]
    for col in all_patient_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    print(f"Converted {len(all_patient_cols)} patient count columns to numeric, handling errors.")

    # --- Impute Key Numeric Columns with Median ---
    numerical_cols_to_impute = [col for col in all_patient_cols if df[col].isnull().any()]
    for col in numerical_cols_to_impute:
        median_value = df[col].median()
        df[col] = df[col].fillna(median_value)
    print(f"Imputed missing values in {len(numerical_cols_to_impute)} patient count columns with the median.")
    
    print("--- Data Loading and Cleaning Complete ---")
    df['ownership']=df['ownership'].replace("Ministry of Health","MOH")
    df['ownership']=df['ownership'].replace("Private Practice","Private")
    return df

# In the same file, e.g., your_app/data_utils.py

def create_average_df(df):
    """
    Takes a cleaned DataFrame and calculates the average monthly patient visits
    for various conditions, returning a new DataFrame with this information.

    Args:
        df (pd.DataFrame): The cleaned DataFrame from load_and_clean_data.

    Returns:
        pd.DataFrame: A new DataFrame containing original identifiers and
                      the calculated average monthly patient loads.
    """
    if df is None:
        return None
        
    print("--- Creating DataFrame with Average Patient Loads ---")
    
    conditions = {
        'Outpatient': [col for col in df.columns if col.startswith('outpatient_')],
        'HIV': [col for col in df.columns if col.startswith('hiv_') and '_dm' not in col and '_htn' not in col],
        'Diabetes': [col for col in df.columns if col.startswith('diabetes_')],
        'Hypertension': [col for col in df.columns if col.startswith('htn_') and 'dm_htn' not in col],
        'DM + HTN': [col for col in df.columns if col.startswith('dm_htn')],
        'HIV + DM': [col for col in df.columns if col.startswith('hiv_dm')],
        'HIV + HTN': [col for col in df.columns if col.startswith('hiv_htn') and '_dm' not in col],
        'HIV + HTN + DM': [col for col in df.columns if col.startswith('hiv_htn_dm')]
    }

    new_avg_cols_dict = {}
    for condition_name, cols in conditions.items():
        if cols:
            new_avg_cols_dict[condition_name] = df[cols].sum(axis=1) / 12

    df_new_cols = pd.DataFrame(new_avg_cols_dict)
    
    # Combine key identifiers with the new average columns
    identifier_cols = ['facility_mfl', 'facility_name', 'county', 'level', 'ownership']
    df_with_averages = pd.concat([df[identifier_cols], df_new_cols], axis=1)
    print("--- DataFrame with Averages Created Successfully ---")
    return df_with_averages