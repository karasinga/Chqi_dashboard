import pandas as pd
import numpy as np
from django.core.cache import cache

import pandas as pd
import numpy as np
from django.core.cache import cache

def load_and_clean_data(filepath=r"redcap_baseline_complete.csv"):
    """
    Loads and cleans the REDCap facility data.
    This function is cached to avoid expensive re-processing on every call.
    """
    cache_key = 'cleaned_redcap_dataframe'
    
    # Try to get the data from the cache first
    df = cache.get(cache_key)
    
    # --- CACHE HIT ---
    # If the dataframe is found, return it immediately.
    if df is not None:
        # print("--- Loading Cleaned DataFrame from CACHE ---")
        return df
        
    # --- CACHE MISS ---
    # If not in cache, run the expensive cleaning process.
    # print("--- Starting Data Loading and Cleaning (Cache Miss) ---")
    
    try:
        df = pd.read_csv(filepath)
    except FileNotFoundError:
        # print(f"Error: Data file not found at {filepath}")
        return None

    # --- Initial Cleaning ---
    if 'Unnamed: 0' in df.columns:
        df.drop(columns=['Unnamed: 0'], inplace=True)
    
    # --- All of your cleaning logic remains here ---
    staff_col_keywords = ['employed', '_start', '_end', '_hiv', '_ncd', '_trained', '_left']
    cols_to_convert = [
        col for col in df.columns 
        if any(keyword in col for keyword in staff_col_keywords) and df[col].dtype == 'float64'
    ]
    df[cols_to_convert] = df[cols_to_convert].fillna(0).astype(int)
    
    placeholders_to_replace = [9999.0, 99999.0, 999999.0, 9999999.0]
    numeric_cols = df.select_dtypes(include=np.number).columns
    for col in numeric_cols:
        df[col] = df[col].replace(placeholders_to_replace, np.nan)
        
    patient_count_prefixes = ['outpatient_', 'hiv_', 'diabetes_', 'htn_', 'dm_htn_', 'hiv_dm_', 'hiv_htn_', 'hiv_htn_dm_']
    all_patient_cols = [col for col in df.columns if any(col.startswith(p) for p in patient_count_prefixes)]
    for col in all_patient_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    numerical_cols_to_impute = [col for col in all_patient_cols if df[col].isnull().any()]
    for col in numerical_cols_to_impute:
        # Check if column has any non-NaN values
        if not df[col].dropna().empty:
            median_value = df[col].median()
        else:
            median_value = 0
        df[col] = df[col].fillna(median_value)
    
    # print("--- Data Cleaning Logic Complete ---")

    # (Minor improvement: Combine replaces into one call with a dictionary)
    df['ownership'] = df['ownership'].replace({
        "Ministry of Health": "MOH",
        "Private Practice": "Private"
    })

    cols_to_update = ['his_hiv', 'his_ncd']
    for col in cols_to_update:
        conditions = [
            df[col].str.contains('emr', case=False, na=False),
            df[col].str.contains('paper', case=False, na=False)
        ]
        choices = ['EMR Based', 'Paper Based']
        df[col] = np.select(conditions, choices, default=df[col])

    # 1. Define the mapping from old text to new text
    care_model_map = {
        'HIV and NCD services are separately located and provided by different providers': 'Separate Location, Different Providers',
        'HIV and NCD services are co-located space and provided by the same provider': 'Co-located, Same Provider',
        'HIV and NCD services are separately located but provided by the same providers': 'Separate Location, Same Provider',
        'HIV and NCD services are co-located but provided by different providers respectively': 'Co-located, Different Providers'
    }

    # 2. Apply the replacement to the column
    df['patients_hivncd_care'] = df['patients_hivncd_care'].replace(care_model_map)

    # --- FINAL STEP BEFORE RETURNING ---
    # Set the fully cleaned DataFrame in the cache.
    # This is OUTSIDE the for loop, but still INSIDE the "cache miss" block.
    # print("--- Storing Cleaned DataFrame in Cache ---")
    cache.set(cache_key, df, timeout=3600) # timeout is 1 hour

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
        
    # print("--- Creating DataFrame with Average Patient Loads ---")
    
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
    # print("--- DataFrame with Averages Created Successfully ---")
    return df_with_averages
