import sys
import os
import re
import json

if __name__ == "__main__":
    if os.path.isfile(sys.argv[1]):
        with open(sys.argv[1], 'r') as f:
            fstr = f.read()
            jstr = re.search(r'({"belts".*?})\n', fstr)
            map_dict = json.loads(jstr.group(1))

            jstr = re.search(r'({"block_name".*?})\n', fstr)
            round_dict = json.loads(jstr.group(1))

        map_size = map_dict["map_size"]
        belts = map_dict["belts"]
        gates = map_dict["gates"]
        walls = map_dict["walls"]

        mines = round_dict["mines"]
        players = round_dict["players"]

        born_1 = []
        born_2 = []
        for p in players:
            if p["player_id"] < 4:
                born_1.append(p)
            else:
                born_2.append(p)

        # 初始化地图
        map_str = [["."] * map_size["width"] for i in range(map_size["height"])]

        # 隧道
        bs = {"up": "^", "right": ">", "down": "v", "left": "<"}
        for b in belts:
            map_str[b["y"]][b["x"]] = bs[b["dir"]]

        # 虫洞
        re = []
        for g in gates:
            name = g["name"]
            if name in re:
                continue
            
            re.append(name)
            gs = []
            for gg in gates:
                if gg["name"] == name:
                    gs.append(gg)

            map_str[gs[0]["y"]][gs[0]["x"]] = chr(gs[0]["name"])
            map_str[gs[1]["y"]][gs[1]["x"]] = chr(gs[0]["name"]).swapcase()
        
        # 岩石
        for w in walls:
            map_str[w["y"]][w["x"]] = "#"

        # 出生点
        for b in born_1:
            map_str[b["y"]][b["x"]] = "O"
        for b in born_2:
            map_str[b["y"]][b["x"]] = "X"

        # 矿点
        for m in mines:
            map_str[m["y"]][m["x"]] = str(m["value"])

        # 地图字符串合成
        mstr = ""
        for ms in map_str:
            mstr += "".join(ms) + os.linesep

        print(mstr)

        result_dict = {
            "game":{
                "revive_player_pos": False,
                "revive_times": 4,
                "vision": 3,
                "power_create_num": 10,
                "timeout": 800
            },
            "map":
            {
                "height": map_size["height"],
                "width": map_size["width"],
                "map_str": mstr
            }
        }
        # print(json.dumps(result_dict, indent=4))
        with open('./map_r2m1.txt', 'w', encoding='utf-8') as f:
            f.write(json.dumps(result_dict, indent=4))


