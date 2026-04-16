"""kwiki/taxonomy.py — 专业/类型分类注册"""
# 分类常量，供其他地方引用
SPECIALTIES = ["arch", "struct", "mech", "hvac", "elec"]
STD_TYPES = ["green", "fire", "general", "seismic", "energy"]
SPECIALTY_NAMES = {
    "arch": "建筑", "struct": "结构", "mech": "给排水",
    "hvac": "暖通", "elec": "电气"
}
STD_TYPE_NAMES = {
    "green": "绿色建筑", "fire": "防火", "general": "通用规范",
    "seismic": "抗震", "energy": "节能"
}