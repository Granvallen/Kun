"""
    by Granvallen
    鲲类实现
"""
import ballclient.service.utils as utils
import random
from queue import PriorityQueue as PQueue # 实现A*用

class Kun:

    def __init__(self, team_id, player_id, force, leg_map, stat):
        self.team_id = team_id
        self.id = player_id
        self.force = force # 势力
        self.vision = leg_map.vision # 视野

        # 保存当前回合运动方向
        self.move = self.random_dir()

        # 下回合该鲲的调度优先级 面对的敌人越多优先级越高 下回合优先调度
        self.priority = 0

        # 记录穿越的虫洞 防止在 探索时 重复穿越 注意应该记录穿越过来后虫洞的坐标
        self.wormhole_pos = (0, 0)

        # 逃脱计时器 由逃跑行为执行后如果敌人消失 在flee_timer回合数内依然保存逃跑状态
        self.flee_timer = 0
        # 记录敌方 或 我方的 行动路线 与距离  用于 狩猎 与 逃跑参考
        self.hf_routes = {} 

        # 用于快速得到行进方向上的坐标
        self.fun = {
            "up": lambda p: (p[0], p[1]-1), 
            "down": lambda p: (p[0], p[1]+1), 
            "left": lambda p: (p[0]-1, p[1]),
            "right": lambda p: (p[0]+1, p[1])
        }

        # probe 路线
        self.next_dir = {"right":"down", "down":"left", "left":"up", "up":"right"}
        # if not stat.probe_dir[self.id]:
        #     self.next_dir = {m:n for n, m in self.next_dir.items()}


        # 一些可调参数
        # 警戒距离 取3 4效果较好
        self.min_flee_dist = 3 # 3 4 
        # 狩猎距离 弃置
        # self.min_hunt_dist = 18
        # 当虫洞距离小于 wormhole_dist 时 探索虫洞
        self.wormhole_dist = 5 # 8
        # 设置flee_timer持续回合数
        self.set_flee_timer = 2 # 2
        # NOTE: 逃跑时 对目的地不可见的邻域距离 加权(分母) 防止传送死亡
        self.flee_dist_weight = 5 # 5
        # hunt的命令等级 level
        self.hunt_level = 10 # 10
        # 巡逻时离边线距离  需要看图的联通情况取值 否则巡逻时会在一个区域打转
        self.probe_margin = self.vision # self.vision
        # 逃跑时控制与边界的距离
        self.flee_margin = self.vision # self.vision
        # 矿的最小收集距离
        self.min_gather_dist = 2*self.vision # 3*self.vision


        # # print("{}队 {}号鲲就位!".format(self.force, self.id))

    def __call__(self, leg_map, stat): # 每只鲲根据 地图 与 战况 做出判断
        # # print("轮到{}号鲲行动!".format(self.id))

        # 记录该鲲这一回合的信息
        for kun_dict in stat.teamkuns.values():
            kun = kun_dict["info"]
            if kun["id"] == self.id:
                self.point = kun["score"]
                self.pos = (kun["x"], kun["y"]) # 该鲲的位置
                self.sleep = kun["sleep"]
                break


        # 该鲲周围的场况 通通用字典
        # # print("{}号鲲正在观察视野...".format(self.id))
        self.vision_map = {"meteor":{}, "tunnel":{}, "wormhole":{}} # 视野内不变的物体
        self.vision_stat = {"power":{}, "teamkuns":{}, "enemykuns":{}} # 视野内在动的物体(不包括自己)
        self.update_vision_map_stat(leg_map, stat) # 更新字典


        # 记录各行动得分 用以排出优先顺序
        self.act_dict = {"probe":0, "gather":0, "hunt":0, "flee":0}
        # 对各行动计分 排出行动优先级 更新act_dict
        self.update_act_dict(leg_map, stat)
        # print("{}号鲲正在思考行动... {}".format(self.id, self.act_dict))


        # # print("{}号鲲正在决定行进方向...".format(self.id))
        # 记录各方向得分
        self.dir_dict = {"stop":-1, "right":0, "up":0, "left":0, "down":0}
        # 去掉不能走的方向 标记为 -1
        self.dir_ban(leg_map, stat)
        # # print("> dir_ban检测点 <")

        # 更新 dir_dict
        for key, val in self.act_dict.items():
            if val != 0: # 为0的行为不执行
                eval("self." + key)(leg_map, stat, self.act_dict[key]) # 调用行动函数 这里用函数名字符串直接调用函数


        # 返回dir_dict值最大的键 即最终方向
        self.move = max(self.dir_dict, key=self.dir_dict.get) # 保留当前行进方向
        # print("{}号鲲决定 {} {}".format(self.id, self.dir_dict, self.move))

        # 更新 pos
        if self.move != "stop":
            self.pos = self.move_to(self.pos, self.move, leg_map)
        
        # return [self.move] if self.move != "stop" else []
        # return []

        # 测试用
        if stat.leg == 1:
            exit()
        else:
            return [self.move] if self.move != "stop" else []


    # 更新该鲲视野内的场况
    def update_vision_map_stat(self, leg_map, stat):
        # 不变的物体
        # 视野内陨石
        for meteor_pos in leg_map.meteor.keys():
            if self.invision(meteor_pos):
                self.vision_map["meteor"][meteor_pos] = -1
        # 视野内隧道
        for tunnel_pos, tunnel_dir in leg_map.tunnel.items():
            if self.invision(tunnel_pos):
                self.vision_map["tunnel"][tunnel_pos] = tunnel_dir
        # 视野内虫洞
        for wormhole_pos, wormhole_out in leg_map.wormhole.items():
            if self.invision(wormhole_pos):
                self.vision_map["wormhole"][wormhole_pos] = wormhole_out

        # 变化的物体
        # 视野内的矿
        for power_pos, power_point in stat.power.items():
            if self.invision(power_pos):
                self.vision_stat["power"][power_pos] = power_point
        # 视野内友军(不包括自己)
        for teamkun_id, teamkun_dict in stat.teamkuns.items():
            if self.invision(teamkun_dict["pos"]) and teamkun_id != self.id:
                self.vision_stat["teamkuns"][teamkun_id] = teamkun_dict

        # 视野内的敌军
        for enemykun_id, enemykun_dict in stat.enemykuns.items():
            if self.invision(enemykun_dict["pos"]):
                self.vision_stat["enemykuns"][enemykun_id] = enemykun_dict

    # 更新行动字典
    def update_act_dict(self, leg_map, stat):
        # 通过几条简单规则对四种行为打分 并确认该鲲的调度优先级

        # NOTE: 逃跑传染 如果3步以内有队友在逃跑 那么该鲲也置为逃跑状态
        if self.force != stat.mode and self.flee_timer == 0:
            for kun_id, act_dict in stat.teamkuns_act_dict.items():
                if len(self.Astar(self.pos, stat.teamkuns_pos[kun_id], leg_map)) <= 3 and act_dict["flee"] != 0:
                    self.flee_timer = 1
                    break


        # if not(self.force == stat.mode and stat.kill_num < 5):
        if self.force == stat.mode or self.force != stat.mode and len(self.vision_stat["enemykuns"]) < 3:
            self.act_dict["gather"] += sum(len(self.Astar(self.pos, pos, leg_map)) < self.min_gather_dist for pos in self.vision_stat["power"].keys())

        # 全体视野内有敌人 狩猎或逃跑
        # print("flee_timer", self.flee_timer)
        if stat.enemykuns != {}:
            self.hf_routes = {} # 记录敌方 或 我方的 行动 与距离

            if self.force == stat.mode: # 优势势力
                # # print("有敌人! 该我们上了!")
                # 优势势力时 计算 自己到所有敌人的行动路线 与 实际距离
                # dist = [] # 记录距离

                # for enemykun_id, enemykun_dict in stat.enemykuns.items():
                #     enemykun_pos = enemykun_dict["pos"]
                #     route = self.Astar(self.pos, enemykun_pos, leg_map)
                #     self.hf_routes[enemykun_id] = {"pos":enemykun_pos, "route":route, "dist":len(route)}

                #     dist.append(len(route))

                # dist = sum(d <= self.min_hunt_dist for d in dist)
                # if dist != 0:
                # NOTE: 改成统一调度
                if stat.target_id != -1 and self.id in stat.hunt_plan_dict.keys():
                    # # print("我将带头冲锋!")
                    self.act_dict["hunt"] += self.hunt_level

            else:
                # # print("有敌人! 小心行动!")
                # 非优势势力时 计算 计算所有敌鲲到我方的行动路线 与 实际距离
                dist = []
                for enemykun_id, enemykun_dict in stat.enemykuns.items():
                    enemykun_pos = enemykun_dict["pos"]
                    route = self.Astar(enemykun_pos, self.pos, leg_map) # 注意此时 是 自己到敌鲲
                    self.hf_routes[enemykun_id] = {"pos":enemykun_pos, "route":route, "dist":len(route)}

                    dist.append(len(route))

                dist = sum(d <= self.min_flee_dist for d in dist)
                if dist != 0:
                    # # print("他们来了!!!")
                    self.act_dict["flee"] += dist
                    self.priority += dist
                    self.flee_timer = self.set_flee_timer
                else:
                    self.priority = 0
                    self.flee_timer = 0

        elif self.flee_timer != 0 and self.force != stat.mode:
            self.flee_timer -= 1
            self.act_dict["flee"] += 1
        else:
            self.priority = 0
            self.flee_timer = 0

        # 最后 不采矿, 逃跑, 狩猎 就去探索
        if sum(self.act_dict.values()) == 0:
            self.act_dict["probe"] += 1

    # 将不能行进的方向标记为 -1
    def dir_ban(self, leg_map, stat):

        # 考虑四个方向
        for d in self.fun.keys():

            # NOTE: 不可达 或 循环无意义
            # # print(d, leg_map.graph[self.pos].values())
            if d not in leg_map.graph[self.pos].values():
                self.dir_dict[d] = -1
                continue

            # 可达的话获得往那个方向走后的坐标
            # NOTE:注意后面讨论的都是这个方向走了之后的坐标
            for pos, move in leg_map.graph[self.pos].items():
                if move == d:
                    move_pos = pos
                    break

            # NOTE: 探索时不进入 除虫洞外的 死胡同
            if self.act_dict["probe"] != 0 and move_pos not in leg_map.wormhole.keys() and len(leg_map.graph[move_pos]) == 1:
                self.dir_dict[d] = -1
                continue

            # NOTE: 处于弱势时 不能自投罗网(走了之后在敌鲲位置) 以及 不能靠近危险(走了之后与敌鲲距离为1)
            # # print("处于弱势时不过分靠近敌人")
            if stat.mode != self.force:
                for enemykun_dict in stat.enemykuns.values():
                    enemykun_pos = enemykun_dict["pos"]
                    # # print(enemykun_pos, len(self.Astar(enemykun_pos, move_pos, leg_map)))
                    # 注意是敌人走到自己的距离
                    # # print(self.Astar(enemykun_pos, move_pos, leg_map)) 这里用曼哈顿距离处理敌人在虫洞上的情况
                    if self.dist(enemykun_pos, self.fun[d](self.pos)) <= 0 or self.dist(enemykun_pos, move_pos) <= 1 or \
                        len(self.Astar(enemykun_pos,move_pos, leg_map)) <= 1:

                        self.dir_dict[d] = -1
                        break

                if self.dir_dict[d] == -1:
                    continue

            # NOTE: 非逃跑时 防止重叠
            # # print("防止重叠", move_pos, stat.teamkuns_pos)
            if self.act_dict["flee"] == 0 and move_pos in stat.teamkuns_pos.values():
                self.dir_dict[d] = -1
                continue


            # NOTE: 防止飞来横祸 在弱势探索 时 不要走不安全的隧道 不靠近隧道出口(容易突然遇到敌人)
            if stat.mode != self.force and self.act_dict["probe"] != 0:
                # 不走不安全隧道
                if self.fun[d](self.pos) not in leg_map.graph.keys() and not self.invision(move_pos):
                    # print("不走隧道")
                    self.dir_dict[d] = -1
                    continue

                # 不靠近隧道出口 除非是我穿越这个隧道到达的出口
                if self.dist(self.pos, move_pos) > self.vision:
                    dir_reverse = {"up":"down", "down":"up", "left":"right", "right":"left"}
                    for move in self.fun.keys():
                        pos = self.fun[move](move_pos)
                        if pos in leg_map.tunnel.keys() and leg_map.tunnel[pos] == dir_reverse[move]:
                            # # print("远离隧道出口")
                            self.dir_dict[d] = -1
                            break




    # 探索
    def probe(self, leg_map, stat, level):

        # NOTE:策略: 保持移动 巡逻
        # 如果之前是停止 或现在不能往之前的方向走 随机选一个能走的方向走
        if self.dir_dict[self.move] == -1:

            moves = []
            dir_reverse = {"up":"down", "down":"up", "left":"right", "right":"left"}
            for move, score in self.dir_dict.items():
                if score != -1:
                    if self.move == "stop":
                        moves.append(move)
                    elif move != dir_reverse[self.move]:
                        # 防止走相反的路
                        moves.append(move)

            if moves != []:
                # print("当前方向无法前进! 随机选择进行方向")
                self.move = self.random_dir(moves)

            else:
                return

        next_pos = self.move_to(self.pos, self.move, leg_map)

        margin = {
            "right": (next_pos[0] + self.probe_margin, leg_map.w),
            "down": (next_pos[1] + self.probe_margin, leg_map.h),
            "left": (self.probe_margin, next_pos[0]),
            "up": (self.probe_margin, next_pos[1])
        }[self.move]

        # 如果视野内有虫洞 探索虫洞
        if self.vision_map["wormhole"] != {}:
            # print("发现虫洞")
            # 遍历视野内 除上次传越过的 虫洞
            for wormhole_pos in self.vision_map["wormhole"].keys():
                # # print(wormhole_pos, self.wormhole_pos)
                if wormhole_pos != self.wormhole_pos: # 非上次穿越过的虫洞
                    self.wormhole_pos = leg_map.wormhole[wormhole_pos]
                    route = self.Astar(self.pos, wormhole_pos, leg_map)

                    if 0 < len(route) <= self.wormhole_dist and self.dir_dict[route[0]] != -1:
                        # print("探索虫洞")
                        self.dir_dict[route[0]] += level
                        return

        if margin[0] >= margin[1] and self.dir_dict[self.next_dir[self.move]] != -1:
            self.dir_dict[self.next_dir[self.move]] += level
            # print("巡逻转弯")
            return

        if self.dir_dict[self.move] != -1:
            # print("保持前进")
            self.dir_dict[self.move] += level

    # 收集
    def gather(self, leg_map, stat, level):
        
        # 找到最有价值的金矿 点数 - 移动距离
        vals = []
        routes = []
        for power_pos, point in self.vision_stat["power"].items():
            # 如果是其他鲲已经打算要采了 跳过
            if power_pos in stat.teamkuns_pos.values():
                continue
            route = self.Astar(self.pos, power_pos, leg_map, stat.teamkuns_pos.values())
            if route == [] or len(route) >= self.min_gather_dist:
                continue

            vals.append(point - len(route))
            routes.append(route)

        if routes != []:
            idx = vals.index(max(vals))
            move = routes[idx][0] # 取出第一个方向
            if self.dir_dict[move] != -1:
                self.dir_dict[move] += level
        elif self.act_dict["flee"] == 0:
            self.probe(leg_map, stat, level)

        # # print("> gather检测点 <")

    # 狩猎
    def hunt(self, leg_map, stat, level):

        if stat.enemykuns == {}: # 没有敌人
            # 保持移动 搜索敌人
            self.probe(leg_map, stat, level)
        else:
            # print("兄弟们上啊!!!")
            # # print(stat.teamkuns_pos.values())
            ban = [pos for pos in stat.teamkuns_pos.values() if pos != stat.hunt_plan_dict[self.id]]
            route = self.Astar(self.pos, stat.hunt_plan_dict[self.id], leg_map, ban)

            if route != [] and self.dir_dict[route[0]] != -1:
                self.dir_dict[route[0]] += level
            else:
                self.dir_dict["stop"] += level

    # 逃跑
    def flee(self, leg_map, stat, level):

        enemykuns_pos = {kun_id:kun_dict["pos"] for kun_id, kun_dict in stat.enemykuns.items()}
        # 计算被敌人封锁的区域
        ban_pos = set(enemykuns_pos.values()) #| self.pos # 自己的位置也算封锁
        ban_pos_predict = set(enemykuns_pos.values())
        for i in range(2):
            ban_pos_predict_temp = set()
            for pos in ban_pos_predict:
                ban_pos_predict_temp |= leg_map.graph[pos].keys()
            ban_pos |= ban_pos_predict_temp
            ban_pos_predict = ban_pos_predict_temp


        # NOTE: 如果允许的话优先走 邻域越多  能快速远离敌人(隧道与虫洞, 不考虑另一边情况未知) 靠近地图中心
        flee_score = {}

        # 遍历所有当前位置的邻域
        for move_pos, move in leg_map.graph[self.pos].items():

            if self.dir_dict[move] == -1:
                continue
            # 逃了之后邻域
            neighbors = leg_map.graph[move_pos]
            # 计算逃跑位置各邻域到自己位置的曼哈顿距离 及 安全邻域个数
            dist_list = []
            safe_neighbor = 0
            for neighbor in neighbors.keys():

                if neighbor not in ban_pos:
                    safe_neighbor += 1

                if self.invision(neighbor):
                    dist_list.append(self.dist(neighbor, self.pos))
                else:
                    dist_list.append(self.dist(neighbor, self.pos) // self.flee_dist_weight)

            flee_score[move] = safe_neighbor + max(dist_list) # - sum(move_pos == pos for pos in stat.teamkuns_pos.values())
            # 往图中心逃再加分
            mg = min(self.pos[0], leg_map.w - self.pos[0] - 1, self.pos[1], leg_map.h - self.pos[1] - 1)
            mg_move = min(move_pos[0], leg_map.w - move_pos[0] - 1) + min(move_pos[1], leg_map.h - move_pos[1] - 1)
            if mg < self.flee_margin:
                flee_score[move] += mg_move

        if flee_score != {}:
            # print("flee_score: ", flee_score)
            self.dir_dict[max(flee_score, key=flee_score.get)] += level

        # NOTE: 如果已经没有安全的路可走 做最后殊死一搏
        # 先计算下所有敌鲲到自己的 实际距离
        routes = {}
        for enemykun_dict in stat.enemykuns.values():
            enemykun_pos = enemykun_dict["pos"]
            routes[enemykun_pos] = self.Astar(enemykun_pos, self.pos, leg_map)

        # 只有当所有路都危险 且有至少一只敌鲲就在当前位置的领域内(不动的话下回合会被干)
        if all(map(lambda x: x == -1, self.dir_dict.values())) and any(map(lambda x: len(x) == 1, routes.values())):

            moves = {}
            # 遍历当前位置所有 没有敌鲲 的邻域 能走的地方
            for move_pos, move in leg_map.graph[self.pos].items():
                
                # 存在 有一个邻域有敌鲲 但这只敌鲲不在视野内 的可能 不过此时也需要孤注一掷
                if move_pos in enemykuns_pos.values():
                    continue

                dist_list = []
                # 遍历所有与自己非相邻的敌鲲 到 move_pos的实际距离
                for enemykun_dict in stat.enemykuns.values():
                    enemykun_pos = enemykun_dict["pos"]
                    # 不考虑已经与自己相邻的鲲 因为认为他们下回合会走到自己的位置
                    if enemykun_pos in leg_map.graph[self.pos].keys():
                        continue

                    dist_list.append(len(self.Astar(enemykun_pos, move_pos, leg_map)))

                if dist_list != []:
                    moves[move] = min(dist_list)
                else:
                    # 当dist_list为空 说明还有地方可以能走(危险) 但所有敌人都已贴身
                    # 这种时候在敌人比较笨的时候还是有逃跑的希望的
                    moves[move] = 0

            if moves != {}:
                # print("殊死一搏!!!", moves)
                good_luck = []
                for move, score in moves.items():
                    if score == max(moves.values()):
                        good_luck.append(move)

                # 随机选择
                # self.dir_dict[self.random_dir(good_luck)] = 0

                # 对于ai来说 选择走距离远的
                move_dict = {}
                for move in good_luck:
                    move_dict[move] = self.dist(self.move_to(self.pos, move, leg_map), self.pos)

                self.dir_dict[max(move_dict, key=move_dict.get)] = 0

            else:
                # 四面楚歌 没有地方能走 鲲卒
                pass

        # # print("> flee检测点 <")


    # 判断是否在视野内
    def invision(self, pos, selfpos=()):
        if selfpos == ():
            selfpos = self.pos
        return  abs(pos[0] - selfpos[0]) <= self.vision and abs(pos[1] - selfpos[1]) <= self.vision

    # 输入为 两坐标元组(x1, y1) (x2, y2) 求 |x1-x2|+|y1-y2|
    def dist(self, m, n):
        return abs(m[0] - n[0]) + abs(m[1] - n[1])

    # A*路径算法 输入为 两坐标元组 返回行进路线
    def Astar(self, From, To, leg_map, ban=[]):

        # TODO: 隐藏的问题: 禁止目录中有To 怎么处理

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

    # 生成随机方向
    def random_dir(self, dir=["up", "down", "left", "right"]):
        return dir[random.randint(0, len(dir)-1)]

    # 输入移动方向 和 当前坐标 返回移动后 坐标
    def move_to(self, pos, move_dir, leg_map):
        for neighbor_pos, move in leg_map.graph[pos].items():
            if move == move_dir:
                return neighbor_pos
