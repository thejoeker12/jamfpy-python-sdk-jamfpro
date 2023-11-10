from datetime import datetime

def compare_dict_keys(dict1, dict2):
    """Returns duplicate keys from 2 supplied dictionaries"""
    dict1_keys = dict1.keys()
    dict2_keys = dict2.keys()
    matched_keys = list(set(dict1_keys) & set(dict2_keys))
    return matched_keys


def format_jamf_datetime(date_time_code):
    """Accepts Jamf style code (i.e last check in) and returns Datetime object for compatibility"""
    datetime_compatible = date_time_code.replace("T", " ").split(".")[0]
    formatted_datetime = datetime.strptime(datetime_compatible, "%Y-%m-%d %H:%M:%S")
    return formatted_datetime
    
                
    