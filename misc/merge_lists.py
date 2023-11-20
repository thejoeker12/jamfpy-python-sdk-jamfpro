import csv

CLASSIC = list(csv.reader(open("output-classic.csv", "r")))[1:]
PRO = list(csv.reader(open("output-pro.csv", "r")))[1:]
CURRENT = list(csv.reader( open("output.csv", "r")))[1:]



def merge(schema) -> dict:
    api_dict = {}
    current_dict = {}
    for line in schema:
        api_dict[line[0]] = {
            "get": line[2],
            "post": line[3],
            "put": line[4],
            "patch": line[5],
            "delete": line[6]
        }


    for line in CURRENT:
        current_dict[line[0]] = {
            "get": line[2],
            "post": line[3],
            "put": line[4],
            "patch": line[5],
            "delete": line[6]
        }

    for endp in api_dict:
        if f"/JSSResource/{endp}" in current_dict:
            print(f"Found: {endp}")
        else:
            print(f"Not Found: {endp}")




def main():
    merge(CLASSIC)


if __name__ == "__main__":
    main()