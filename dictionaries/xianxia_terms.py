"""Thuật ngữ Tu Chân / Tiên Hiệp / Light Novel Trung Quốc.

Đây là seed data thủ công cho các thuật ngữ phổ biến trong Tiên Hiệp / Tu Chân
novel mà không có trong các từ điển open-source.

Tích hợp vào build_hanviet_dict.py qua --seed-file argument.
"""

# ============================================================================
# Thuật ngữ Tu Chân / Tiên Hiệp - các giai đoạn tu luyện, công pháp, v.v.
# ============================================================================

XIANXIA_TERMS: dict[str, str] = {
    # ===== Cảnh giới tu luyện (cultivation realms) =====
    "炼气": "Luyện Khí",
    "炼气期": "Luyện Khí Kỳ",
    "筑基": "Trúc Cơ",
    "筑基期": "Trúc Cơ Kỳ",
    "金丹": "Kim Đan",
    "金丹期": "Kim Đan Kỳ",
    "元婴": "Nguyên Anh",
    "元婴期": "Nguyên Anh Kỳ",
    "化神": "Hóa Thần",
    "化神期": "Hóa Thần Kỳ",
    "炼虚": "Luyện Hư",
    "炼虚期": "Luyện Hư Kỳ",
    "合体": "Hợp Thể",
    "合体期": "Hợp Thể Kỳ",
    "大乘": "Đại Thừa",
    "大乘期": "Đại Thừa Kỳ",
    "渡劫": "Độ Kiếp",
    "飞升": "Phi Thăng",
    "仙人": "Tiên Nhân",
    "散仙": "Tán Tiên",
    "天仙": "Thiên Tiên",
    "金仙": "Kim Tiên",
    "大罗金仙": "Đại La Kim Tiên",
    "准圣": "Chuẩn Thánh",
    "圣人": "Thánh Nhân",
    "天道": "Thiên Đạo",

    # ===== Linh căn / căn cơ =====
    "灵根": "Linh Căn",
    "天灵根": "Thiên Linh Căn",
    "变异灵根": "Biến Dị Linh Căn",
    "单灵根": "Đơn Linh Căn",
    "双灵根": "Song Linh Căn",
    "三灵根": "Tam Linh Căn",
    "四灵根": "Tứ Linh Căn",
    "五灵根": "Ngũ Linh Căn",
    "伪灵根": "Ngụy Linh Căn",
    "废灵根": "Phế Linh Căn",

    # ===== Tài nguyên tu luyện =====
    "灵石": "Linh Thạch",
    "上品灵石": "Thượng Phẩm Linh Thạch",
    "中品灵石": "Trung Phẩm Linh Thạch",
    "下品灵石": "Hạ Phẩm Linh Thạch",
    "极品灵石": "Cực Phẩm Linh Thạch",
    "灵药": "Linh Dược",
    "仙草": "Tiên Thảo",
    "灵草": "Linh Thảo",
    "灵丹": "Linh Đan",
    "仙丹": "Tiên Đan",
    "丹药": "Đan Dược",
    "灵兽": "Linh Thú",
    "妖兽": "Yêu Thú",
    "仙鹤": "Tiên Hạc",
    "法宝": "Pháp Bảo",
    "灵宝": "Linh Bảo",
    "先天灵宝": "Tiên Thiên Linh Bảo",
    "后天灵宝": "Hậu Thiên Linh Bảo",
    "仙器": "Tiên Khí",
    "神器": "Thần Khí",
    "魔器": "Ma Khí",

    # ===== Pháp thuật / Công pháp =====
    "功法": "Công Pháp",
    "神通": "Thần Thông",
    "法术": "Pháp Thuật",
    "阵法": "Trận Pháp",
    "剑诀": "Kiếm Quyết",
    "心法": "Tâm Pháp",
    "内功": "Nội Công",
    "外功": "Ngoại Công",
    "剑意": "Kiếm Ý",
    "拳意": "Quyền Ý",
    "杀意": "Sát Ý",
    "道心": "Đạo Tâm",
    "魔功": "Ma Công",
    "邪功": "Tà Công",
    "正派": "Chính Phái",
    "邪派": "Tà Phái",
    "魔门": "Ma Môn",
    "魔道": "Ma Đạo",
    "修道": "Tu Đạo",
    "悟道": "Ngộ Đạo",
    "得道": "Đắc Đạo",

    # ===== Kiếm (vũ khí) =====
    "仙剑": "Tiên Kiếm",
    "飞剑": "Phi Kiếm",
    "御剑": "Ngự Kiếm",
    "剑修": "Kiếm Tu",
    "剑道": "Kiếm Đạo",
    "剑意": "Kiếm Ý",
    "剑灵": "Kiếm Linh",
    "剑意": "Kiếm Ý",

    # ===== Cảnh giới võ giả (võ hiệp) =====
    "后天": "Hậu Thiên",
    "先天": "Tiên Thiên",
    "宗师": "Tông Sư",
    "大宗师": "Đại Tông Sư",
    "武圣": "Võ Thánh",
    "武帝": "Võ Đế",
    "绝世": "Tuyệt Thế",

    # ===== Yêu ma quỷ quái =====
    "妖族": "Yêu Tộc",
    "魔族": "Ma Tộc",
    "鬼族": "Quỷ Tộc",
    "神族": "Thần Tộc",
    "修罗": "Tu La",
    "阿修罗": "A Tu La",
    "阎王": "Diêm Vương",
    "阎罗": "Diêm La",

    # ===== Vị trí / tổ chức =====
    "天庭": "Thiên Đình",
    "地府": "Địa Phủ",
    "九重天": "Cửu Trọng Thiên",
    "三界": "Tam Giới",
    "凡界": "Phàm Giới",
    "仙界": "Tiên Giới",
    "魔界": "Ma Giới",
    "妖界": "Yêu Giới",
    "神界": "Thần Giới",

    # ===== Môn phái / tông môn =====
    "宗门": "Tông Môn",
    "门派": "Môn Phái",
    "教派": "Giáo Phái",
    "圣地": "Thánh Địa",
    "禁地": "Cấm Địa",
    "秘境": "Bí Cảnh",
    "洞府": "Động Phủ",
    "闭关": "Bế Quan",
    "出关": "Xuất Quan",
    "掌门": "Triệu Môn",
    "长老": "Trưởng Lão",
    "堂主": "Đường Chủ",
    "护法": "Hộ Pháp",
    "弟子": "Đệ Tử",
    "内门弟子": "Nội Môn Đệ Tử",
    "外门弟子": "Ngoại Môn Đệ Tử",
    "真传弟子": "Chân Truyền Đệ Tử",

    # ===== Danh xưng tu sĩ =====
    "道友": "Đạo Hữu",
    "前辈": "Tiền Bối",
    "后辈": "Hậu Bối",
    "师叔": "Sư Thúc",
    "师伯": "Sư Bá",
    "师兄": "Sư Huynh",
    "师姐": "Sư Tỷ",
    "师弟": "Sư Đệ",
    "师妹": "Sư Muội",

    # ===== Chiến đấu / sự kiện =====
    "渡天劫": "Độ Thiên Kiếp",
    "天劫": "Thiên Kiếp",
    "心魔": "Tâm Ma",
    "走火入魔": "Tẩu Hỏa Nhập Ma",
    "爆体": "Bạo Thể",
    "夺舍": "Đoạt Xá",
    "转世": "Chuyển Thế",
    "轮回": "Luân Hồi",

    # ===== Vật phẩm thần kỳ =====
    "储物袋": "Trữ Vật Đới",
    "储物戒": "Trữ Vật Giới",
    "灵舟": "Linh Chu",
    "飞舟": "Phi Chu",
    "传送阵": "Truyền Tống Trận",

    # ===== Cấp bậc / đẳng cấp =====
    "天骄": "Thiên Kiêu",
    "妖孽": "Yêu Nhiệt",
    "绝世天才": "Tuyệt Thế Thiên Tài",
    "废材": "Phế Tài",
    "天才": "Thiên Tài",
    "凡体": "Phàm Thể",
    "灵体": "Linh Thể",
    "圣体": "Thánh Thể",
    "神体": "Thần Thể",
    "魔体": "Ma Thể",

    # ===== Khác =====
    "修炼": "Tu Luyện",
    "修行": "Tu Hành",
    "历练": "Lịch Luyện",
    "机缘": "Cơ Duyên",
    "造化": "Tạo Hóa",
    "气运": "Khí Vận",
    "命格": "Mệnh Cách",
    "天道誓言": "Thiên Đạo Thệ Ngôn",
    "心魔誓": "Tâm Ma Thệ",
}


# ============================================================================
# Thuật ngữ Đô Thị / Hiện đại (Modern/Urban novels)
# ============================================================================

URBAN_TERMS: dict[str, str] = {
    "总裁": "Tổng Giám Đốc",
    "CEO": "Giám Đốc Điều Hành",
    "董事长": "Chủ Tịch Hội Đồng Quản Trị",
    "总经理": "Tổng Quản Lý",
    "副总经理": "Phó Tổng Quản Lý",
    "部门经理": "Trưởng Phòng",
    "总监": "Giám Sát",
    "主管": "Chủ Quản",
    "助理": "Trợ Lý",
    "秘书": "Thư Ký",
    "前台": "Lễ Tân",
    "实习生": "Thực Tập Sinh",
    "合伙人": "Đối Tác",
    "股东": "Cổ Đông",
    "董事": "Giám Đốc",
    "副总裁": "Phó Tổng Giám Đốc",

    # Trường học
    "班主任": "Giáo Viên Chủ Nhiệm",
    "辅导员": "Cố Vấn",
    "校长": "Hiệu Trưởng",
    "副校长": "Phó Hiệu Trưởng",
    "教务处": "Phòng Giáo Vụ",
    "教导主任": "Chủ Nhiệm Giáo Vụ",
    "宿舍": "Ký Túc Xá",
    "寝室": "Phòng Ngủ",

    # Y tế
    "急诊科": "Khoa Cấp Cứu",
    "内科": "Khoa Nội",
    "外科": "Khoa Ngoại",
    "妇产科": "Khoa Phụ Sản",
    "儿科": "Khoa Nhi",
    "主任医师": "Chủ Nhiệm Khoa",
    "副主任医师": "Phó Chủ Nhiệm Khoa",
    "主治医师": "Bác Sĩ Chính",
    "住院医师": "Bác Sĩ Nội Trú",
    "护士长": "Trưởng Điều Dưỡng",

    # Cảnh sát
    "刑警": "Hình Sự Cảnh Sát",
    "片警": "Cảnh Sát Khu Vực",
    "重案组": "Đội Trọng Án",
    "特警": "Đặc Cảnh",
    "武警": "Vũ Cảnh",
    "派出所": "Công An Phường",
    "公安局": "Cục Công An",
    "检察院": "Viện Kiểm Sát",
    "法院": "Tòa Án",
    "律师": "Luật Sư",

    # Gia đình
    "公婆": "Bố Mẹ Chồng",
    "岳父": "Bố Vợ",
    "岳母": "Mẹ Vợ",
    "丈母娘": "Mẹ Vợ",
    "亲家": "Thông Gia",
}


# ============================================================================
# Thuật ngữ Kiếm Hiệp / Võ Hiệp (Wuxia/Martial Arts)
# ============================================================================

WUXIA_TERMS: dict[str, str] = {
    "内力": "Nội Lực",
    "真气": "Chân Khí",
    "真元": "Chân Nguyên",
    "元气": "Nguyên Khí",
    "丹田": "Đan Điền",
    "经脉": "Kinh Mạch",
    "穴道": "Huyệt Đạo",
    "任脉": "Nhâm Mạch",
    "督脉": "Đốc Mạch",
    "奇经八脉": "Kỳ Kinh Bát Mạch",
    "武林盟主": "Võ Lâm Minh Chủ",
    "武林大会": "Võ Lâm Đại Hội",
    "华山论剑": "Hoa Sơn Luận Kiếm",
    "绝世高手": "Tuyệt Thế Cao Thủ",
    "一代宗师": "Nhất Đại Tông Sư",
    "武功秘籍": "Võ Công Bí Kíp",
    "绝学": "Tuyệt Học",
    "轻功": "Khinh Công",
    "暗器": "Ám Khí",
    "点穴": "Điểm Huyệt",
    "解穴": "Giải Huyệt",
    "打通任督二脉": "Thông Nhâm Đốc Nhị Mạch",
    "打通经脉": "Thông Kinh Mạch",
    "打坐": "Đả Tọa",
    "运功": "Vận Công",
    "真气外放": "Chân Khí Ngoại Phóng",
    "以气御剑": "Dĩ Khí Ngự Kiếm",
    "剑气": "Kiếm Khí",
    "刀气": "Đao Khí",
    "拳风": "Quyền Phong",
    "掌风": "Chưởng Phong",
    "内伤": "Nội Thương",
    "走火入魔": "Tẩu Hỏa Nhập Ma",
    "疗伤": "Liệu Thương",
    "解毒": "Giải Độc",
}


# All terms combined
ALL_SEED_TERMS: dict[str, str] = {**XIANXIA_TERMS, **URBAN_TERMS, **WUXIA_TERMS}


# ============================================================================
# Nhân vật lịch sử Trung Quốc nổi tiếng (xuất hiện trong nhiều light novel)
# ============================================================================

HISTORICAL_FIGURES: dict[str, str] = {
    # Triều đại
    "秦始皇": "Tần Thủy Hoàng",
    "汉武帝": "Hán Vũ Đế",
    "唐太宗": "Đường Thái Tông",
    "宋太祖": "Tống Thái Tổ",
    "成吉思汗": "Thành Cát Tư Hãn",
    "武则天": "Võ Tắc Thiên",

    # Tam Quốc
    "刘备": "Lưu Bị",
    "关羽": "Quan Vũ",
    "张飞": "Trương Phi",
    "赵云": "Triệu Vân",
    "诸葛亮": "Gia Cát Lượng",
    "曹操": "Tào Tháo",
    "司马懿": "Tư Mã Ý",
    "周瑜": "Chu Du",
    "吕布": "Lữ Bố",
    "貂蝉": "Điêu Thuyền",
    "西施": "Tây Thi",
    "王昭君": "Vương Chiêu Quân",
    "杨贵妃": "Dương Quý Phi",
    "杨玉环": "Dương Ngọc Hoàn",

    # Tây Du Ký
    "孙悟空": "Tôn Ngộ Không",
    "唐僧": "Đường Tăng",
    "猪八戒": "Trư Bát Giới",
    "沙僧": "Sa Tăng",
    "沙悟净": "Sa Ngộ Tịnh",
    "观音": "Quán Âm",
    "观音菩萨": "Quán Âm Bồ Tát",
    "如来": "Như Lai",
    "如来佛祖": "Như Lai Phật Tổ",
    "太上老君": "Thái Thượng Lão Quân",
    "玉皇大帝": "Ngọc Hoàng Đại Đế",
    "王母娘娘": "Vương Mẫu Nương Nương",

    # Hồng Lâu Mộng & các tác phẩm cổ điển
    "贾宝玉": "Giả Bảo Ngọc",
    "林黛玉": "Lâm Đại Ngọc",
    "薛宝钗": "Tuyết Bảo Thoa",
    "王熙凤": "Vương Hý Phượng",

    # Nhà thơ / văn hào nổi tiếng
    "李白": "Lý Bạch",
    "杜甫": "Đỗ Phủ",
    "白居易": "Bạch Cư Dị",
    "王维": "Vương Duy",
    "苏轼": "Tô Thức",
    "苏东坡": "Tô Đông Pha",
    "李清照": "Lý Thanh Chiếu",
    "辛弃疾": "Tân Quế Tật",
    "陆游": "Lục Du",
    "陶渊明": "Đào Uyên Minh",
    "屈原": "Khuất Nguyên",
    "司马迁": "Tư Mã Thiên",
    "孔子": "Khổng Tử",
    "老子": "Lão Tử",
    "庄子": "Trang Tử",
    "孟子": "Mạnh Tử",
    "墨子": "Mặc Tử",
    "韩非子": "Hàn Phi Tử",
    "孙子": "Tôn Tử",
    "诸葛亮": "Gia Cát Lượng",
    "鬼谷子": "Quỷ Cốc Tử",
    "华佗": "Hoa Đà",
    "张仲景": "Trương Trọng Cảnh",
    "李时珍": "Lý Thời Trân",
}

ALL_SEED_TERMS: dict[str, str] = {
    **XIANXIA_TERMS,
    **URBAN_TERMS,
    **WUXIA_TERMS,
    **HISTORICAL_FIGURES,
}