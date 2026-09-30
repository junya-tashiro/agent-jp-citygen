"""Authored urban building families; dimensions are design values in metres."""
from dataclasses import dataclass
@dataclass(frozen=True)
class BuildingSpec:
    key:str
    title:str
    family:str
    width:float
    depth:float
    floors:int
    floor_height:float
    base_height:float
    wall:str
    frame:str
    glass:str
    description:str

CATALOG=(
 BuildingSpec('building_01','BUILDING 01','fin_tower',48,36,34,3.85,10.8,'limestone','bronze','blue_glass','縦フィンの高層棟と、列柱・吹抜けロビー・屋上庭園の低層部'),
 BuildingSpec('building_02','BUILDING 02','stone_tower',44,34,30,3.9,5.8,'pale_stone','dark_metal','grey_glass','石の基壇、深い格子窓、二段のセットバック'),
 BuildingSpec('building_03','BUILDING 03','split_tower',52,38,38,3.9,10.5,'concrete','silver','blue_glass','高さの異なる二つの棟、縦のスリット、広い商業基壇'),
 BuildingSpec('building_04','BUILDING 04','chamfer_tower',42,32,27,3.8,9.6,'dark_stone','bronze','grey_glass','隅切りの輪郭、低層の二層店舗窓、濃い金属の大枠'),
 BuildingSpec('building_05','BUILDING 05','wide_office',57,23,8,3.65,5.1,'pale_stone','silver','grey_glass','横長の既存オフィス、奥行きのある横連窓と段階的な改修'),
 BuildingSpec('building_06','BUILDING 06','pencil',10.8,18,10,3.45,4.7,'concrete','silver','blue_glass','細いガラス面と不透明な縦コア、奥まった入口'),
 BuildingSpec('building_07','BUILDING 07','punched',17,19,9,3.35,4.5,'tile','dark_metal','grey_glass','タイル壁の独立窓、後退する上階、石張りの店舗階'),
 BuildingSpec('building_08','BUILDING 08','ribbon',21,17,9,3.4,4.6,'granite','bronze','smoke_glass','隅切り角地、横連窓、段差のある屋上と独立した店舗入口'),
 BuildingSpec('building_09','BUILDING 09','balcony',13.5,19,8,3.5,4.8,'concrete','silver','blue_glass','深い避難バルコニーと縦長のガラス面、金属手摺'),
 BuildingSpec('building_10','BUILDING 10','brick',19,21,7,3.7,5.2,'brick','dark_metal','grey_glass','レンガの大きな窓割、補強フレームと改修された店舗階'),
 BuildingSpec('building_11','BUILDING 11','round_blade',48,34,40,3.95,11,'limestone','silver','blue_glass','曲面の角、ずれた頂部、水平帯と縦格子、大きな低層の軒'),
 BuildingSpec('building_12','BUILDING 12','soft_step',45,38,32,3.85,9.8,'pale_stone','bronze','grey_glass','丸い輪郭が段階的に後退する石とガラスの高層棟'),
 BuildingSpec('building_13','BUILDING 13','offset_pair',52,35,36,3.9,10.4,'concrete','silver','blue_glass','偏心する二棟、深い縦の間隙、連結ブリッジ'),
 BuildingSpec('building_14','BUILDING 14','terrace_tower',43,33,29,3.8,9.6,'dark_stone','bronze','grey_glass','非対称に重なるボリュームと複数の空中テラス'),
 BuildingSpec('building_15','BUILDING 15','round_ribbon',22,19,11,3.5,4.8,'pale_stone','silver','blue_glass','柔らかい角を回り込む横連窓と後退したペントハウス'),
 BuildingSpec('building_16','BUILDING 16','folded_office',27,21,10,3.55,5.2,'concrete','silver','grey_glass','折板状のガラス面と奥まる方立、角度で変わる反射'),
 BuildingSpec('building_17','BUILDING 17','steel_loft',15,22,10,3.8,5.0,'dark_stone','dark_metal','grey_glass','外付けの柱梁・斜材と大きな工房窓、深い入口'),
 BuildingSpec('building_18','BUILDING 18','ceramic_screen',19,23,9,3.55,5.1,'brick','bronze','grey_glass','陶板の縦スクリーンとガラス面、上階のセットバック'),
 BuildingSpec('building_19','BUILDING 19','arcade_office',29,23,9,3.65,5.3,'limestone','bronze','smoke_glass','厚い石のアーケード、深い窓、落ち着いた中層オフィス'),
 BuildingSpec('building_20','BUILDING 20','garden_steps',25,25,11,3.6,5.2,'concrete','silver','blue_glass','三段の庭園テラス、窓とバルコニー、低層の緑陰'),
 BuildingSpec('building_21','BUILDING 21','round_blade',82,57,42,4.0,17,'pale_stone','silver','blue_glass','広い床面積と四層の商業ギャラリー、丸い高層棟'),
 BuildingSpec('building_22','BUILDING 22','terrace_tower',72,60,35,3.9,14,'limestone','bronze','grey_glass','大きな街区型基壇と二階の連続テラス'),
 BuildingSpec('building_23','BUILDING 23','steel_loft',7.2,17,9,3.5,4.5,'dark_stone','dark_metal','grey_glass','狭い間口、独立した店舗とオフィス入口'),
 BuildingSpec('building_24','BUILDING 24','ceramic_screen',6.8,15,8,3.4,4.5,'brick','bronze','grey_glass','細い陶板外壁と小さなテナント店舗'),

 BuildingSpec('building_25','BUILDING 25','terrace_tower',52,46,36,3.9,14,'limestone','bronze','grey_glass','地下駐車場への車路と受付・エレベーターホールを持つ高層ビル'),
 BuildingSpec('building_26','BUILDING 26','steel_loft',18,21,10,3.5,4.5,'pale_stone','dark_metal','grey_glass','1階に小型コンビニと独立した上階入口を持つ雑居ビル'),


)
def get_spec(key):
    for spec in CATALOG:
        if spec.key==key or spec.family==key:return spec
    raise ValueError('Unknown building: '+str(key))
