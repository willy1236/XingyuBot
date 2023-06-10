import random,math

def generate_area(m, n):
    area = [['0' for _ in range(n)] for _ in range(m)]
    
    # 隨機生成區域
    for i in range(m):
        for j in range(n):
            destence_00 = int(math.fabs(i-0))**2 + int(math.fabs(j-0))**2
            destence_mn = int(math.fabs(m-i))**2 + int(math.fabs(n-j))**2
            if destence_00 <= 9 or destence_mn <= 9:
                chance_1 = 0.2
            elif destence_00 <= 25 or destence_mn <= 25:
                chance_1 = 0.4
            else:
                chance_1 = 0.5

            area[i][j] = random.choices(['0', '1'],[1-chance_1,chance_1])[0]
    
    # 確保左上角和右下角都是空地
    area[0][0] = '0'
    area[m-1][n-1] = '0'
    
    # 確保左上角有至少一條路徑可以走到右下角
    area[0][1] = '0'
    area[1][0] = '0'

    area[m-1][n-2] = '0'
    area[m-2][n-1] = '0'
    
    return area

def dfs(area, visited, i, j):
    # 如果已經訪問過這個位置，直接返回
    if visited[i][j]:
        return
    
    # 標記這個位置為已訪問
    visited[i][j] = True
    
    # 搜尋上下左右四個方向
    if i > 0 and area[i - 1][j] == '0':
        dfs(area, visited, i - 1, j)
    if j > 0 and area[i][j - 1] == '0':
        dfs(area, visited, i, j - 1)
    if i < len(area) - 1 and area[i + 1][j] == '0':
        dfs(area, visited, i + 1, j)
    if j < len(area[0]) - 1 and area[i][j + 1] == '0':
        dfs(area, visited, i, j + 1)

def is_reachable(area):
    # 創建一個與 area 一樣大小的 visited 陣列
    visited = [[False for _ in range(len(area[0]))] for _ in range(len(area))]
    
    # 從左上角開始搜尋
    dfs(area, visited, 0, 0)
    
    # 如果右下角被訪問過，表示有路徑可以到達
    return visited[-1][-1]

# 測試程式碼
def sunmon_area(l,w):
    print('sun')
    area = None
    while not area:
        area = generate_area(l, w)
        reachable = is_reachable(area)
        if not reachable:
            area = None
        print(not area)
    return area