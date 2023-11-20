import csv

CLASSIC = list(csv.reader(open("output-classic.csv", "r")))[1:]
PRO = list(csv.reader(open("output-pro.csv", "r")))[1:]
CURRENT = list(csv.reader( open("output-new.csv", "r")))[1:]

found = []
not_found = []
out_dict = {}

def merge(schema, api) -> dict:
    api_dict = {}
    current_dict = {}
    methods = ["get", "post", "put", "patch", "delete"]
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
        out_dict[endp] = api_dict[endp]
        if endp in current_dict:
            out_blob = api_dict[endp]
            for m in methods:
                if out_blob[m] == "N/A":
                    pass
                else:
                    out_blob[m] = current_dict[endp][m]

            out_dict[endp] = out_blob

    print(out_dict)

    with open("Master.csv", "w") as file:
            file.write(f"url,api,get,post,put,patch,delete\n")
            for i in out_dict:
                get = out_dict[i]["get"]
                post = out_dict[i]["post"]
                put = out_dict[i]["put"]
                patch = out_dict[i]["patch"]
                delete = out_dict[i]["delete"]
                file.write(f"{i},{api},{get},{post},{put},{patch},{delete}\n")



            







def main():
    merge(CLASSIC, "classic")
    merge(PRO, "pro")


if __name__ == "__main__":
    main()