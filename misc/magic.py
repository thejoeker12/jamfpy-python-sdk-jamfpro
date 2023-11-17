from pprint import pprint

hold = []
lines_with_tick = []
master = {}
with open("misc/README.md", "r", encoding="UTF-8") as file:
    file = file.read()
    file_split = file.split("\n")
    for line in file_split:
        if line:
            if "✅" in line:
                lines_with_tick.append(line)


for line in lines_with_tick[1:]:
    split = line.split()
    tick_index = split.index("✅")
    for i in range(0, tick_index + 1):
        split.pop(0)

    method = split[0].replace("*","")
    url = split[1].replace("`", "")
    if len(url) > 2:
        if "/" in url:
            hold.append(method)

            if url not in master:
                master[url] = [method]

            if url in master:
                if method not in master[url]:
                    master[url].append(method)


pprint(master)
print(list(set(hold)))

with open("output.csv", "w") as file:
    file.write("url,api,get,post,put,patch,delete\n")
    for url in master:
        methods = {
            "GET": False,
            "PUT": False,
            "PATCH": False,
            "DELETE": False,
            "POST": False
        }

        api = "classic" if "jssresource" in url.lower() else "pro"

        for method in master[url]:
            methods[method] = True

        get = "False" if not methods["GET"] else "True"
        put = "False" if not methods["PUT"] else "True"
        patch = "False" if not methods["PATCH"] else "True"
        delete = "False" if not methods["DELETE"] else "True"
        post = "False" if not methods["POST"] else "True"

        out_str = f"{url},{api},{get},{post},{put},{patch},{delete}\n"

        file.write(out_str)


