import json

# 定義 Event 類別
class Event:
    def __init__(self, event_data, participant_mapping):
        self.type = event_data.get('type', 'UNKNOWN')
        self.timestamp = event_data.get('timestamp', 'N/A')
        self.participant_id = str(event_data.get('participantId', 'N/A'))
        self.actor = participant_mapping.get(self.participant_id, 'Unknown Participant') if self.participant_id != 'N/A' else 'N/A'
        self.details = event_data  # 儲存完整事件資料
        
        # 擊殺相關
        self.killer_id = str(event_data.get('killerId', 'N/A'))
        self.killer = participant_mapping.get(self.killer_id, 'Unknown Participant') if self.killer_id != 'N/A' else 'N/A'
        self.victim_id = str(event_data.get('victimId', 'N/A'))
        self.victim = participant_mapping.get(self.victim_id, 'Unknown Participant') if self.victim_id != 'N/A' else 'N/A'
        self.assist_ids = [str(pid) for pid in event_data.get('assistingParticipantIds', [])]
        self.assists = [participant_mapping.get(pid, 'Unknown Participant') for pid in self.assist_ids]
        
        # 建築與守衛相關
        self.creator_id = str(event_data.get('creatorId', 'N/A'))
        self.creator = participant_mapping.get(self.creator_id, 'Unknown Participant') if self.creator_id != 'N/A' else 'N/A'
        
        # 怪物擊殺相關
        self.monster_type = event_data.get('monsterType', 'N/A')
        self.building_type = event_data.get('buildingType', 'N/A')
        self.ward_type = event_data.get('wardType', 'N/A')
    
    def __str__(self):
        base_info = f"Event: {self.type}, Timestamp: {self.timestamp}, Actor: {self.actor}"
        
        if self.type == 'ITEM_PURCHASED':
            return f"{base_info}, Item ID: {self.details.get('itemId', 'N/A')}"
        if self.type == 'SKILL_LEVEL_UP':
            return f"{base_info}, Skill Slot: {self.details.get('skillSlot', 'N/A')}"
        if self.type == 'LEVEL_UP':
            return f"{base_info}, Level: {self.details.get('level', 'N/A')}"
        if self.type == 'WARD_PLACED':
            return f"{base_info}, Creator: {self.creator}, Ward Type: {self.ward_type}"
        if self.type == 'CHAMPION_KILL':
            assist_text = f", Assists: {', '.join(self.assists)}" if self.assists else ""
            return (f"{base_info}, Killer: {self.killer}, Victim: {self.victim}{assist_text}")
        if self.type == 'BUILDING_KILL':
            return f"{base_info}, Killer: {self.killer}, Building Type: {self.building_type}"
        if self.type == 'ELITE_MONSTER_KILL':
            return f"{base_info}, Killer: {self.killer}, Monster Type: {self.monster_type}"
        
        return base_info



# 讀取 JSON 檔案
with open('test/Untitled-1.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

# 提取 frames
frames = data['info']['frames']

# 提取參與者名稱 (如有)
participants = data['metadata']['participants']
participant_mapping = {str(i + 1): participants[i] for i in range(len(participants))}

# 逐幀解析
for i, frame in enumerate(frames):
    print(f"\n=== Frame {i + 1} ===")
    print(f"Timestamp: {frame['timestamp']} ms")
    
    # 分析事件 (events)
    print("\n-- Events --")
    events = frame.get('events', [])
    event_objects = [Event(event, participant_mapping) for event in events]
    for event in event_objects:
        print(event)
    
    # 分析玩家資訊 (participantFrames)
    print("\n-- Participant Frames --")
    participant_frames = frame.get('participantFrames', {})
    for participant_id, stats in participant_frames.items():
        champion_stats = stats.get('championStats', {})
        position = stats.get('position', {})
        total_gold = stats.get('totalGold', 0)
        xp = stats.get('xp', 0)
        actor = participant_mapping.get(participant_id, 'Unknown Participant')
        
        print(f"Participant {actor}: Position({position['x']}, {position['y']}), Gold: {total_gold}, XP: {xp}")
