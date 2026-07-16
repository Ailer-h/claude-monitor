import json

def get_dict(filepath: str) -> dict:
    '''
    Accesses a JSON file and returns it as a dictionary
    '''

    try:
        with open(filepath, 'r') as json_file:
            data = json.load(json_file)
            return data
    except FileNotFoundError:
        print(f"File {filepath} not found")
        return {}

def save_dict(json_path: str, dictionary: dict) -> None:
    '''
    Updates an existing JSON file
    '''
    try:
        with open(json_path, 'w') as json_file:
            json.dump(dictionary, json_file, indent=4)
    except FileNotFoundError:
        print(f"File {json_path} not found")