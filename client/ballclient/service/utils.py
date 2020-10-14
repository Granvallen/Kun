"""
    by Granvallen
"""

import ballclient.service.constants as constants
from queue import PriorityQueue as PQueue # 实现A*用

# 地图信息
class Map:

    def __init__(self, map_dict):
        self.w = map_dict["width"]
        self.h = map_dict["height"]

        self.vision = map_dict["vision"]

        # 重新记录三种特殊地形
        self.meteor = {} # 陨石 为了统一也用字典
        self.tunnel = {} # 隧道 值是隧道方向
        self.wormhole = {} # 虫洞 键值对是一组虫洞
        for obj in map_dict["meteor"]:
            self.meteor[(obj["x"], obj["y"])] = -1
        for obj in map_dict["tunnel"]:
            self.tunnel[(obj["x"], obj["y"])] = obj["direction"]
        for obj in map_dict["wormhole"]:
            # 如果虫洞坐标已经在values中 说明已经处理过了
            if (obj["x"], obj["y"]) in self.wormhole.values():
                continue
            else:
                # 寻找他的对应虫洞
                for jbo in map_dict["wormhole"]:
                    if jbo["name"].swapcase() == obj["name"]:
                        self.wormhole[(obj["x"], obj["y"])] = (jbo["x"], jbo["y"])
                        self.wormhole[(jbo["x"], jbo["y"])] = (obj["x"], obj["y"])
        
        # 生成图
        self.init_graph()

    # 生成一张能快速索引出相邻节点的图 用于路径搜索
    def init_graph(self):
        # graph格式 graph = { (0, 0): {(0, 1):"down", (1, 0):"right"} } 值为邻域节点列表
        # 若没有邻节点 为 []
        self.graph = {}

        # 用于快速得到行进方向上的坐标
        fun = {
            "up": lambda x, y: (x, y-1), 
            "down": lambda x, y: (x, y+1), 
            "left": lambda x, y: (x-1, y),
            "right": lambda x, y: (x+1, y)
        }

        # 遍历所有地图坐标
        for x in range(self.w):
            for y in range(self.h):
                # 如果当前位置为 陨石 或 隧道 则跳过
                if (x, y) in {**self.meteor, **self.tunnel}.keys():
                    continue

                # 至于普通地形与虫洞一样处理
                self.graph[(x, y)] = {}
                
                # 考虑其周围的四个方向
                for d in fun.keys():
                    m_x, m_y = fun[d](x, y) # 计算得到移动后的坐标

                    # 判断该座标是否出界 出界则跳过
                    if not(0 <= m_x < self.w and 0 <= m_y < self.h):
                        continue

                    # 判断是否是特殊地形
                    # 陨石的话就直接跳过
                    if (m_x, m_y) in self.meteor.keys():
                        continue
                    # 隧道的话一直走到出来 需要检测循环!
                    elif (m_x, m_y) in self.tunnel.keys():
                        # 连续穿越隧道
                        tunnel_list = [(x, y)]
                        while (m_x, m_y) in self.tunnel.keys():
                            if (m_x, m_y) not in tunnel_list: 
                                tunnel_list.append((m_x, m_y))
                            else: # 发生隧道循环
                                break
                            # 穿过隧道
                            m_x, m_y = fun[self.tunnel[(m_x, m_y)]](m_x, m_y)
                        
                        # 只有当出来是 普通地形 或 虫洞 才记录为邻节点
                        # 虫洞
                        if (m_x, m_y) in self.wormhole.keys():
                            self.graph[(x, y)][self.wormhole[(m_x, m_y)]] = d
                        # 普通地形
                        elif (m_x, m_y) not in {**self.meteor, **self.tunnel}.keys() and \
                            (m_x, m_y) != (x, y):
                            self.graph[(x, y)][(m_x, m_y)] = d

                    # 虫洞 将虫洞的另一个出口作为邻节点
                    elif (m_x, m_y) in self.wormhole.keys():
                        self.graph[(x, y)][self.wormhole[(m_x, m_y)]] = d
                    else: # 非特殊地形 作为普通邻节点
                        self.graph[(x, y)][(m_x, m_y)] = d


# 回合场况信息
class Status:

    def __init__(self, teams_dict):
        self.team_id = constants.team_id

        for team in teams_dict:
            if team["id"] == self.team_id:
                self.teamkuns_id = team["players"]
                self.force = team["force"]
            else:
                self.enemykuns_id = team["players"]

        # 给每只鲲确定巡逻方向
        self.probe_dir = {}
        for i in range(4):
            self.probe_dir[self.teamkuns_id[i]] = True if i < 2 else False

        # 半场
        self.leg = 0

        # 鲲字典
        self.teamkuns = {}
        self.enemykuns = {}

        # 猎杀调度  {kun_id: 目标地点}
        self.hunt_plan_dict = {}
        
        # 锁定的敌鲲id
        self.target_id = -1
        # 击杀数 这个击杀数可能与实际击杀数不同 只包括在策略中击杀的目标数
        self.kill_num = 0

        # 记录各鲲的行动字典
        self.teamkuns_act_dict = {}



        # 可调参数
        # 最小目标分数 hunt_score要比min_target_score大 加入候选目标
        # NOTE: 如果地图很难发现敌人的话降低阈值
        self.min_target_score = -16 # -16
        # 目标切换过冲阈值 防止频繁切换目标
        self.target_change = 5 # 5
        # 有虫洞放弃追捕的最小距离 虫洞在地图中间的话调小一点
        self.min_wormhole_dist = 6 # 6
        # 最大预测距离
        self.max_predict_dist = 5 # 5
        # 是否完全锁定(除非目标失踪)
        self.islockalong = False # False


    # 更新
    def update(self, stat_dict, leg_map):

        self.round_id = stat_dict["round_id"]
        self.mode = stat_dict["mode"] # 该回合优势势力

        # 能量 注意当没有能量时 是没有 power 这个键的
        self.power = {}
        if "power" in stat_dict.keys():
            for power in stat_dict["power"]:
                self.power[(power["x"], power["y"])] = power["point"]


        # 记录teamkuns这回合移动要移动到的位置 防止鲲重合
        self.teamkuns_pos = {}

        self.teamkuns_act_dict = {}

        # 下一回合调度优先级
        self.kunpriority = {}

        # # print("> update检测点1 <")
        # 鲲字典
        teamkuns = {}
        enemykuns = {}
        # # print(stat_dict)
        # 两队的鲲
        for kun in stat_dict["players"]:
            # # print(kun)
            if kun["team"] == self.team_id:
                teamkuns[kun["id"]] = {"info":kun, "pos":(kun["x"], kun["y"])}
            else:
                enemykuns[kun["id"]] = {"info":kun, "pos":(kun["x"], kun["y"])}
        # # print("> update检测点2 <")

        # 判断上一回合是否有鲲阵亡
        # # print(len(teamkuns), len(self.teamkuns))
        if len(teamkuns) < len(self.teamkuns) and len(enemykuns) < 4:
            # print("有鲲被捕杀, 定位元凶!")
            # 找到阵亡的鲲
            for teamkun_id, teamkun_pos in self.teamkuns_pos.items():
                if teamkun_id not in teamkuns.keys():
                    # print(teamkun_id, "号鲲阵亡")
                    # 如果 阵亡鲲位置没有视野 添加一个该位置的敌鲲
                    enemykuns_pos = {enemykun_id:enemykun_dict["pos"] for enemykun_id, enemykun_dict in enemykuns.items()}
                    
                    if teamkun_pos not in enemykuns_pos.values():

                        guess_id = list(self.enemykuns_id - enemykuns.keys())[0]
                        enemykuns[guess_id] = {"info":{}, "pos":teamkun_pos}
        # 更新
        self.teamkuns = teamkuns
        self.enemykuns = enemykuns
        # # print("kuns更新检测点")


        # 队伍状态
        for team in stat_dict["teams"]:
            if team["id"] == self.team_id:
                self.team_point = team["point"]
                self.team_life = team["remain_life"]
            else:
                self.enemy_point = team["point"]
                self.enemy_life = team["remain_life"]


        # 当自己方强势 且发现敌鲲 且我方鲲数目大于2 开始组织猎杀
        if self.mode == self.force and self.enemykuns != {} and len(self.teamkuns) >= 2:
            self.lock_target(leg_map)
            if self.target_id != -1:
                # print("猎杀目标", self.target_id, "号鲲(冷酷)")
                self.hunt_plan(leg_map)
        else:
            self.target_id = -1

    # 当我方进攻时 发现敌鲲 进行捕获锁定
    def lock_target(self, leg_map):
        # 如果已经锁定 继续追杀目标
        if self.islockalong and self.target_id in self.enemykuns.keys():
            return

        # 遍历视野内的每只敌鲲
        hunt_score = {}
        for enemykun_id, enemykun_dict in self.enemykuns.items():
            
            enemykun_pos = enemykun_dict["pos"]

            # 先看下敌人到虫洞距离 太近就不追了
            # TODO: 这里有个问题 当已经封锁成功后 如果敌鲲距离虫洞很近 依然会放弃追捕
            min_dist = [len(self.Astar(enemykun_pos, wormhole_pos, leg_map, self.teamkuns_pos.values())) for wormhole_pos in leg_map.wormhole.keys()]
            if any([0 < dist < self.min_wormhole_dist for dist in min_dist]):
                continue
            # print("min_dist", min_dist)

            # 携带分值越高越好
            enemykun_score = enemykun_dict["info"]["score"]

            # 计算 我方所有鲲到该鲲的距离
            dist = [] # 记录距离
            for teamkun_dict in self.teamkuns.values():
                teamkun_pos = teamkun_dict["pos"]
                
                route = self.Astar(teamkun_pos, enemykun_pos, leg_map)

                dist.append(len(route))

            # 只考虑距离最近的三只
            if len(dist) > 3:
                dist.sort()
                dist.pop()

            # 平均距离越小越好
            dist_mean = sum(dist) // len(dist)

            # 距离边缘的最小值 越靠边缘越好
            mg = min(enemykun_pos[0], leg_map.w - enemykun_pos[0] - 1) + min(enemykun_pos[1], leg_map.h - enemykun_pos[1] - 1)

            hunt_score_temp = enemykun_score - dist_mean - mg
            # print("hunt_score_temp: ", hunt_score_temp)
            # 这个分数要足够大才 加入候选目标
            if hunt_score_temp > self.min_target_score:
                hunt_score[enemykun_id] = hunt_score_temp

        # 另外当已经在围捕一个目标时 新目标需要比原目标大 self.target_change 才更换目标 防止频繁更换目标
        if hunt_score != {}:
            target_id_new = max(hunt_score, key=hunt_score.get)
            # 如果当前没有目标 或 原目标已不满足要求
            if self.target_id == -1 or self.target_id not in hunt_score.keys():
                self.target_id = target_id_new
            elif hunt_score[target_id_new] > hunt_score[self.target_id] + self.target_change:
                self.target_id = target_id_new

        else:
            self.target_id = -1


    # 猎杀调度 策略2 代号: 窒息
    def hunt_plan(self, leg_map):
        # # print("> hunt_plan检测点 <")

        self.hunt_plan_dict = {}
        # 目标位置
        target_pos = self.enemykuns[self.target_id]["pos"]
        # 我方所有可调度鲲的id
        teamkuns_id = list(self.teamkuns.keys())
        # 我方所有鲲的当前坐标
        teamkuns_pos = {kun_id:kun_dict["pos"] for kun_id, kun_dict in self.teamkuns.items()}
        # 取出目标所有邻域(只要能走的)
        target_neighbor_pos = leg_map.graph[target_pos].keys()
        # print("target_pos", target_pos)
        # print("teamkuns_pos", teamkuns_pos)


        # NOTE: 确定我方鲲的行动优先级 合理性很重要 处于不利位置的鲲先进行分配
        teamkun_route = {} # {kun_id : route}
        teamkun_order = {} # {kun_id : score}
        for kun_id in teamkuns_id:
            # 越靠近旁边的鲲优先级越高
            kun_pos = teamkuns_pos[kun_id]
            route = self.Astar(kun_pos, target_pos, leg_map)
            teamkun_route[kun_id] = route
            teamkun_order[kun_id] = min(kun_pos[0], leg_map.w - kun_pos[0] - 1) + min(kun_pos[1], leg_map.h - kun_pos[1] - 1) + \
                len(leg_map.graph[kun_pos].keys() & target_neighbor_pos) + len(route)

        teamkun_order = dict(sorted(teamkun_order.items(), key=lambda x:x[1], reverse=False)) # 从小到大 排
        # 更新优先级 让追捕的鲲先调度
        order = 3
        for kun_id in teamkun_order.keys():
            self.kunpriority[kun_id] = order
            order -= 1
        # print("teamkun_order", teamkun_order)



        # 追捕策略
        # 计算到我方行动时 已经实体封锁的区域 所谓实体封锁 就是由 鲲 石头 边界组成的封锁 不包括预测的部分
        ban_tight = set(teamkuns_pos.values()) | leg_map.meteor.keys()
        # I.如果目标鲲已经无路可逃 且我方用于封锁的鲲能到目标 给最后一击
        if all(map(lambda neighbor_pos: neighbor_pos in ban_tight, target_neighbor_pos)) and \
            any(map(lambda pos: target_pos in leg_map.graph[pos].keys(), leg_map.graph[target_pos].keys())):

            # print(self.target_id, "号鲲, 再见（づ￣3￣）づ╭❤～")
            # 选择一只封锁的鲲去了结他
            for kun_id in teamkun_order.keys():
                if teamkuns_pos[kun_id] in target_neighbor_pos:
                    self.hunt_plan_dict[kun_id] = target_pos
                    self.kill_num += 1
                    return

        # II.判断能否完成实体封锁
        if sum(len(r) <= 2 for r in teamkun_route.values()) >= len(target_neighbor_pos):
            # # print("申请联合封锁行动")
            record = {}
            # 需要考虑的鲲 由可能进入目标邻域的鲲
            kuns_id = {kun_id for kun_id, kun_route in teamkun_route.items() if len(kun_route) <= 2}
            # 遍历所有目标邻域
            for neighbor_pos in target_neighbor_pos:
                # 找出能进入该邻域的鲲
                neighbor_kuns = {kun_id for kun_id in kuns_id if len(self.Astar(teamkuns_pos[kun_id], neighbor_pos, leg_map)) <= 1}

                if neighbor_kuns == set():
                    break
                else:
                    # 先记录一下
                    record[neighbor_pos] = neighbor_kuns
            # print("record", record)
            # 所有邻域都有可能的时候 再继续处理
            if record.keys() == target_neighbor_pos:
                # kun_all = set()
                # for k in record.values():
                #     kun_all |= k
                # # print(kun_all == kuns_id)
                re = self.Btfun(kuns_id, list(record.values()), teamkun_route)
                
                if re != []:
                    # print("申请联合行动通过!")
                    for kun_id, pos in zip(re, list(record.keys())):
                        if pos != teamkuns_pos[kun_id] and pos not in self.hunt_plan_dict.values(): 
                            # 如果被分配的位置不在自己的位置 且 那个位置还没有设置过
                            self.hunt_plan_dict[kun_id] = pos

                    # 最后看下在邻域已经全部封锁的情况下 有没有 到目标距离为1 且 还没调度的鲲 给目标最后一击
                    for kun_id in kuns_id:
                        if kun_id not in self.hunt_plan_dict.keys() and len(teamkun_route[kun_id]) == 1:
                            # print(self.target_id, "号鲲, 再见（づ￣3￣）づ╭❤～")
                            self.hunt_plan_dict[kun_id] = target_pos
                            self.kill_num += 1
                            return
                    
                    # 判断一下用于封锁的鲲下回合有没有能力干掉目标 如果目标到其邻域是单向的 则还需要另外队友
                    if any(map(lambda pos: target_pos in leg_map.graph[pos].keys(), leg_map.graph[target_pos].keys())):
                        return


        # III.如果目标还有逃路 分配兵力进行围堵
        # 每只鲲按优先级单独处理
        for kun_id in teamkun_order.keys():
            kun_pos = teamkuns_pos[kun_id]

            # 找出 在该鲲行动前 所有 除该鲲邻域以外 封锁的位置
            # 包括所有我方鲲的位置 和 该鲲以外我方鲲的邻域 计划过的鲲的位置及邻域 最后是陨石位置
            ban_pos = set(teamkuns_pos.values()) | set(self.hunt_plan_dict.values()) | leg_map.meteor.keys()
            # 加入我方鲲的邻域
            for pos in teamkuns_pos.values():
                if pos != kun_pos: # 除该鲲以外的邻域
                    ban_pos |= leg_map.graph[pos].keys()
            # 这里不把该鲲的邻域加上是因为后面该鲲会移动 邻域也在变 之前的邻域就不能封锁了
            # NOTE: 考虑一下 计划过鲲的邻域 要不要纳入考虑
            # for pos in self.hunt_plan_dict.values():
            #     ban_pos |= leg_map.graph[pos].keys()

            # 分析敌人能走的邻域 这个邻域基于之前已经调度过鲲的位置 
            # NOTE: 在预测敌人的时候把该鲲邻域加上 这个封锁区域作为之后的参照 到底动了好多少
            ban_pos_stop = ban_pos | leg_map.graph[kun_pos].keys()
            # NOTE: 目标可能移动的邻域(考虑了封锁, 与target_neighbor_pos区别) 后面的预测应该基于此展开
            target_move_pos = {pos for pos in target_neighbor_pos if pos not in ban_pos_stop}
            # print("target_move_pos", target_move_pos)
            # 计算预测的回合数
            route = teamkun_route[kun_id]


            # round_n == 1 考虑的是 目标的邻域
            if len(route) > self.max_predict_dist:
                round_n = self.max_predict_dist
            else:
                round_n = len(route)
            # print("round_n", round_n)
            # 记录所有候选坐标的得分
            c_score = {}

            # 记录n回合敌人逃跑坐标 对于每一只鲲处理时 flee_pos是一样的
            flee_pos = set()
            neighbor_round = target_move_pos
            flee_pos |= neighbor_round
            # 计算n回合敌人逃跑坐标
            for n in range(round_n):
                neighbor_round_temp = set()
                for pos in neighbor_round:
                    neighbor_round_temp |= {p for p in leg_map.graph[pos].keys() if p not in ban_pos}
                flee_pos |= neighbor_round_temp
                neighbor_round = neighbor_round_temp
            # # print("flee_pos", flee_pos)


            # NOTE: 1 考虑鲲动的情况 遍历该鲲的邻域
            for kun_neighbor_pos in leg_map.graph[kun_pos].keys():

                # 如果这个方向距离远了 跳过
                neighbor_route = self.Astar(kun_neighbor_pos, target_pos, leg_map)

                # 只有距离目标为1的鲲 才可能后退
                if len(neighbor_route) > len(route) > 1:
                    continue

                # 判断是否对目标完成实体封锁
                ban_tight_move = ban_tight | {kun_neighbor_pos}
                if all(map(lambda neighbor_pos: neighbor_pos in ban_tight_move, target_neighbor_pos)):
                    c_score[kun_neighbor_pos] = 100
                    break

                # 更新这么移动后封锁的坐标 添加移动坐标 与 其 邻域
                ban_pos_move = ban_pos | leg_map.graph[kun_neighbor_pos].keys() | {kun_neighbor_pos}
                # # print("ban_pos_move", ban_pos_move)

                score = sum(n_pos in ban_pos_move for n_pos in flee_pos)
                # # print("score", score)

                c_score[kun_neighbor_pos] = score


            # NOTE: 2
            # 只有距离目标为1的鲲才考虑停止的情况
            if len(route) <= 1 or flee_pos == set() and len(route) <= 2:
                # 考虑该鲲不动
                score = sum(n_pos in ban_pos_stop for n_pos in flee_pos)
                c_score[kun_pos] = score
            elif c_score != {} and sum(s for s in c_score.values()) == 0:
                # 如果距离不是1 又没有起到封锁的作用 让该鲲先前往目标
                # # print("距离目标太远, 快速行进")
                self.hunt_plan_dict[kun_id] = target_pos
                continue




            # 最终确定该鲲的移动
            # print(kun_id, c_score)
            # 取分数最大的坐标为行动目标
            if c_score != {}:
                # 处理有多个最大值的情况
                max_score = max(c_score.values())
                max_score_pos = {pos:score for pos, score in c_score.items() if score == max_score}
                # 最大值唯一
                if len(max_score_pos) == 1:
                    self.hunt_plan_dict[kun_id] = max(max_score_pos, key=max_score_pos.get)
                else:
                    # 非唯一的话再考虑离边界距离
                    for pos in max_score_pos.keys():
                        max_score_pos[pos] += min(pos[0], leg_map.w - pos[0] - 1) + min(pos[1], leg_map.h - pos[1] - 1)
                    self.hunt_plan_dict[kun_id] = max(max_score_pos, key=max_score_pos.get)

                # self.hunt_plan_dict[kun_id] = max(c_score, key=c_score.get)
            else:
                self.hunt_plan_dict[kun_id] = target_pos


        # print(self.hunt_plan_dict)



    # 输入为 两坐标元组(x1, y1) (x2, y2) 求 |x1-x2|+|y1-y2|
    def dist(self, m, n):
        return abs(m[0] - n[0]) + abs(m[1] - n[1])

    # A*路径算法 输入为 两坐标元组 返回行进路线
    def Astar(self, From, To, leg_map, ban=[]):
        
        cameFrom = {} # 记录父节点
        gScore = {}
        fScore = {}

        openSet = PQueue()
        closeSet = []

        gScore[From] = 0
        fScore[From] = gScore[From] + self.dist(From, To)
        openSet.put((fScore[From], From)) # 起始点入队
        cameFrom[From] = From
        
        while not openSet.empty():

            current = openSet.get()[1] # 取出队首元素坐标
            closeSet.append(current)


            if (current == To): # 到达目的地
                # route存移动坐标
                # route = [current]
                # while current in cameFrom.keys() and current != From:
                #     current = cameFrom[current] # 取出current父节点
                #     route.append(current)
                
                # route存移动方向
                route = []
                while current in cameFrom.keys() and current != From:
                    parent = cameFrom[current] # 取出current父节点
                    route.append(leg_map.graph[parent][current])
                    current = parent
                # 列表倒转
                route.reverse()
                # # print(route)

                return route



            # 遍历相邻节点
            for neighbor in leg_map.graph[current].keys():
                

                if neighbor in closeSet or neighbor in ban:
                    continue

            
                gScore_temp = gScore[current] + 1 # 由于每一步代价相同所以都加1
                fScore_temp = gScore_temp + self.dist(neighbor, To)
            

                if neighbor not in gScore.keys():
                    openSet.put((fScore_temp, neighbor))
                elif gScore_temp >= gScore[neighbor]:
                    continue
            
                cameFrom[neighbor] = current
                gScore[neighbor] = gScore_temp
                fScore[neighbor] = fScore_temp

        return []

    # 输入 [{1}, {1,2}, {2,4}]
    def Btfun(self, kun_all, record, teamkun_route):
        if kun_all == set() or record[0] == set():
            return []

        # 选择鲲的时候从与目标距离远的鲲开始选
        pick_list = {kun_id:len(teamkun_route[kun_id]) for kun_id in record[0]}
        pick_list = dict(sorted(pick_list.items(), key=lambda x:x[1], reverse=True))

        for kun_id in pick_list.keys():
            # 如果此鲲可以分配给这个邻域
            if kun_id in kun_all:
                
                if len(record) == 1:
                    return [kun_id]

                kun_all_t = kun_all - {kun_id}
                record_t = record[1:]
                re = self.Btfun(kun_all_t, record_t, teamkun_route)
                if re != []:
                    re = [kun_id] + re
                    return re
        return []