"""
    by Granvallen
"""

import ballclient.service.constants as constants
import ballclient.service.kun as kun
import ballclient.service.utils as utils
import time

teamkuns = {} # 己方的鲲 {kun_id:kun_class}
teamkuns_pos = {}
leg_map = None # 半场地图
stat = None # 回合场况
goal = [0, 0]
leg = 0

# 半场开始 一场比赛分上下半场 每半场300回合 有2种模式 每种模式持续150回合
def leg_start(msg):
    """
        {
            "msg_name":"leg_start"，   #leg开始消息名
            "msg_data": {
                "map":{                 #地图信息
                    "width":15,         #地图宽度（X坐标）
                    "height":15,        #地图长度（Y坐标）
                    "vision":3,         #视野范围
                    "meteor": [         #陨石坐标
                        {"x":1,"y":1},
                        {"x":1,"y":4}
                    ],
                    "tunnel": [         #时空隧道的坐标和方向
                        {"x":3,"y":1, "direction":"down"},
                        {"x":3,"y":4, "direction":"down"}
                    ],
                    "wormhole": [      #虫洞的坐标和名称 a<->A b<->B
                        {"name":"a",x":4,"y":1},
                        {"name":"A",x":4,"y":4}
                    ]
                },
                "teams":[         #各队及Tank ID
                    {"id":1001,"players":[0,1,2,3],"force":"beat"},
                    {"id":1002,"players":[4,5,6,7],"force":"think"}
                ]
            }
        } 
    """

    # print("半场开始!")

    global teamkuns, leg_map, stat, leg
    teamkuns = {} # 半场开始重新实例化鲲

    # print("更新地图...")
    leg_map = utils.Map(msg['msg_data']['map']) # 更新地图

    stat = utils.Status(msg['msg_data']['teams']) # 实例化 status
    stat.leg = leg

    # print("队员上场...")
    for kun_id in stat.teamkuns_id:
        teamkuns[kun_id] = kun.Kun(stat.team_id, kun_id, stat.force, leg_map, stat)


# 上下半场结束
def leg_end(msg):
    """
        {
            "msg_name" : "leg_end",
            "msg_data" : {
                "teams" : [
                    {
                        "id" : 1001,    # 队ID
                        "point" : 770   # 本leg的各队所得点数
                    },
                    {
                    "id" : 1002,
                    "point" : 450
                    }
                ]
            }
        }
    """
    global goal, leg
    # print("半场结束!")
    leg += 1
    teams = msg["msg_data"]['teams']
    # 打印比赛得分
    for i, team in enumerate(teams):
        print ("teams: %s" % team['id'])
        print ("point: %s" % team['point'])
        goal[i] += team['point']

# 回合  输入字典 返回字典
def round(msg):
    """
        输入字典
        {
            "msg_name":"round",      # 回合消息名
            "msg_data":{
                "round_id":2,        # 回合标识，要求参赛选手在响应消息回填
                "mode":"beat"        # 本回合优势势力，在一定回合后切换
                "power": [           # 能量的坐标与价值
                    {"x":5,"y":2, "point":1},
                    {"x":5,"y":5, "point":2}
                ],
                "players":[          # sleep表示该player是否处于睡眠
                    {
                        "id":0,"score":0,"sleep":0,"team":1001,"x":0,"y":1
                    },
                    ....              # 如果有多个player信息的话
                ],
                "teams":[           # 各队当前的分数、剩余复活次数
                    {"id":1001,"point":0, "remain_life":2},
                    {"id":1002,"point":0, "remain_life":3}
                ]
            }
        }
        注: 
        "power" 只包含视野范围内的矿点, 每个矿的价值是知道的.
        "players" 包含自己，同时也包含视野范围内的敌人.

        输出字典
        {
            "msg_name": "action",     # 动作请求消息名
            "msg_data": {
                "round_id": 2,        # 回合标识，回填
                "actions": [
                    {
                        "team": 1002, 
                        "player_id": 5,
                        "move": ["up"],         #移动方向，不动为空[]
                    }, 
                    .... #如果有多个player动作需要反馈的话
                ]
            }
        }
    """
    global teamkuns, leg_map, stat

    round_id = msg['msg_data']['round_id']
    # print("------ round: {} ------".format(round_id))

    # 合成返回消息
    result = {
        "msg_name": "action",
        "msg_data": {
            "round_id": round_id
        }
    }

    # 当我方全灭时直接返回
    if "players" not in msg['msg_data']:
        # print("我方全灭...")
        result['msg_data']['actions'] = []
        return result


    # # print("更新场况...")

    # 场况 每回合初始化
    stat.update(msg['msg_data'], leg_map)

    # 当非围捕行动时 需要从kun那里确认这一回合的调度优先级 其实只在逃跑时用到优先级
    # 有围捕行动时 调度优先级由 stat 决定
    if stat.target_id == -1:
        for kun_id in stat.teamkuns.keys():
            stat.kunpriority[kun_id] = teamkuns[kun_id].priority

    stat.kunpriority = dict(sorted(stat.kunpriority.items(), key=lambda x:x[1], reverse=True)) # 从大到小
    # # print("stat.kunpriority", stat.kunpriority)

    # start = time.clock()

    action = []
    for kun_id in stat.kunpriority.keys():
        kun = teamkuns[kun_id]
        move = kun(leg_map, stat)
        stat.teamkuns_pos[kun_id] = kun.pos
        stat.teamkuns_act_dict[kun_id] = kun.act_dict
        
        action.append({
            "team": kun.team_id, "player_id": kun_id,
            "move": move
        })

    # end = time.clock()
    # # print(end - start, "s")

    result['msg_data']['actions'] = action

    return result








# 游戏结束
def game_over(msg):
    print ("游戏结束!")
    print("比分 {} : {}".format(goal[0], goal[1]))
