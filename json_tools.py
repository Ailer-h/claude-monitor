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