# Agent-Centric Japanese City Generator

[English](README.md)

コーディングエージェントから扱うことを中心に設計した、日本の都市・街並みの生成器です。
日本の道路や交差点を中心に、車線・路面標示・信号・標識・歩道・点字ブロック・街路樹など、街路を構成する形状や設備の作り込みを重視しています。
道路網に沿って建物やコインパーキング、地下鉄入口を配置し、Blenderの都市シーンを生成します。

![多様な建物、街路樹、歩道、点字ブロックを備えた生成都市の交差点](media/intersection_reverse.jpg)

## エージェントと街を作る

「200m四方に大通りと生活道路を配置し、信号なし交差点を一つ入れたい」といった要望を、コーディングエージェントに伝えて制作します。
エージェントは要求JSONを編集し、共通のCLIで計画・検証・生成を行います。
道路の制約や建物配置の計算は生成器が担当するため、街ごとにモデリングコードを書き直す必要はありません。

**自然言語の要望 → エージェントが要求JSONを作成 → 配置計画・SVG地図 → Blenderで街を生成**

形状・素材・テクスチャはコードから生成し、外部のモデル・画像アセットを必要としません。
日本語文字には利用者が用意するフォントを使用します。詳細は [依存とライセンス](docs/PROVENANCE.md)。
本プロジェクトのモデリングと生成処理の実装は、Codexとの対話を通じて制作しています。
利用時は特定のエージェントに依存せず、JSONとCLIを扱えるコーディングエージェントから操作できます。

## まず試す

必要環境: Python 3.10以降、Node.js 18以降、Blender 4.5 LTS。
macOSで検証。その他OSはパスを指定できるが、実機検証は未実施。
通常利用にnpm install、GUIサーバー、LLM APIキーは不要。

```sh
# 日本語フォントは利用条件を確認して自分で用意する。
export CITY_FONT=/absolute/path/to/JapaneseFont.ttf
# macOSの既定パス以外なら指定
export BLENDER_BIN=/absolute/path/to/blender

python3 city.py capabilities
python3 city.py plan examples/city/central_200.json --output scenes/demo/plan.json
python3 city.py preview scenes/demo/plan.json --output scenes/demo/output
```

`scenes/demo/output/city.blend`、`overview.png`、`street.png` が出力されます。
画像不要なら `preview` の代わりに `build`。同じ計画・ファイルハッシュなら生成済みBlendを再利用します。
同じ場所に異なる計画を出す際は `--replace` を明示するか、別の出力先を指定してください。

## 上から見た地図

`plan` と同時にSVG地図を出力します。道路・歩道・建物敷地と階数・駐車場・地下鉄入口・信号有無を、Blender起動前に確認できます。
保存した計画からの再出力はPythonだけで行えます。

```sh
python3 city.py map scenes/demo/plan.json --output scenes/demo/map.svg
```

ブラウザーで開いて拡大できます。縮尺付きの配置概略図で、建物の屋根形状や路面標示は省略しています。

## エージェントへ渡す例

> docs/AGENT_WORKFLOW.mdに従って街を作ってください。
> 200m四方で、中央に片側2車線の大通り一本、片側1車線の道路を複数。
> 信号なし十字路を一つ入れ、高層ビルと雑居ビルを混ぜてください。
> ライブラリ本体は変更せず、scenes/my_cityに計画と結果を保存してください。

エージェントは要求JSONを編集します。自然言語を解釈する専用モデルは同梱しません。

## 都市を構成する機能

- 直線・曲線、十字路・丁字路、信号あり/なし、1〜3車線、中央分離帯、歩道と各種設備。
- 26の建物原型。16原型は構成をseedから計画し、寸法・平面・外壁・低層用途・屋上などを変更可能。
- 沿道の建物配置、占有領域・敷地への収まりの検証、駐車場車路の切り欠き、曲線沿いの舗装接続。
- 地下鉄入口（階段・エレベーター）、コインパーキング、街路樹・植え込み・信号・標識など。
- 計画と全設計値の保存、数値検証、EEVEE確認画像、生成時間・容量の記録。

![建物と歩道が連続する並木の大通り](media/street_depth.jpg)

建物の自動配置は保守的な矩形敷地を使用します。棟数と形状比率は目標であり、実現結果と警告を出力します。
高低差や不整形敷地への建物変形は未対応。建築設計・道路設計の法規適合を保証するものではありません。

## アセット一覧

| 建物の低層内装 | コインパーキング | 地下鉄入口 |
|:---:|:---:|:---:|
| [![コンビニの売り場とロビーの内装](media/building_store_detail.jpg)](media/building_store_detail.jpg) | [![駐車区画、フラップ、看板、精算機](media/parking.jpg)](media/parking.jpg) | [![駅名看板を備えたガラス張りのエレベーター入口](media/subway_elevator.jpg)](media/subway_elevator.jpg) |
| [建物](asset_library/building/README.md) | [コインパーキング](asset_library/coin_parking/README.md) | [地下鉄入口](asset_library/subway_entrance/README.md) |

各アセットの引数・寸法・原点・生成方法は、個別のREADMEを参照してください。

| 種類 | 内容 |
|---|---|
| [建物](asset_library/building/README.md) | 高層ビル・雑居ビル、低層内装、地下駐車場入口 |
| [コインパーキング](asset_library/coin_parking/README.md) | 駐車区画、フラップ、精算機、看板、囲い |
| [地下鉄入口](asset_library/subway_entrance/README.md) | 階段・エレベーター、駅名・路線表示 |
| [車両用信号機](asset_library/traffic_signal/README.md) | 車両灯器、矢印灯器、支持構造 |
| [歩行者用信号機](asset_library/pedestrian_signal/README.md) | 人物表示、カウントダウン、支持構造 |
| [道路標識](asset_library/road_sign/README.md) | 規制・案内の標識面と支柱 |
| [路面標示](asset_library/road_marking/README.md) | 自転車レーン標示・進行方向矢印 |
| [横断防止柵](asset_library/guardrail/README.md) | 歩道沿いのパイプ柵 |
| [反射ポール](asset_library/reflector_pole/README.md) | 反射帯付きの車線分離ポール |
| [カーブミラー](asset_library/curve_mirror/README.md) | 一面・二面の凸面鏡と支柱 |
| [二灯式警告灯](asset_library/dual_warning_lamp/README.md) | 縦型のアンバー色警告灯 |
| [街灯](asset_library/street_light/README.md) | 車道用・歩道用の灯具 |
| [街路樹](asset_library/street_tree/README.md) | 樹形・寸法・個体差を持つ落葉高木 |
| [植え込み](asset_library/planting/README.md) | 低木・剪定された生垣 |
| [消火栓蓋](asset_library/fire_hydrant_cover/README.md) | 長方形の鋳鉄蓋 |
| [消火栓標識](asset_library/fire_hydrant_sign/README.md) | 消火栓の位置を示す標識 |
| [街路設備](asset_library/street_utilities/README.md) | 排水口・設備蓋・制御盤 |

### 共通部品

[shared](asset_library/shared/README.md) は、舗装・金属・葉群・フォントなど、アセット間で共有する処理を提供します。

## 作例・仕様

- `examples/city/central_200.json`: 200m四方、幹線＋生活道路、信号なし十字路。
- `examples/city/avenue_500.json`: 500m道路・29棟・駐車場2か所・地下鉄2種類。
- `examples/city/avenue_360.json`: 地下駐車場、コインパーキング、地下鉄2種類。
- `examples/city/curved_300.json`: 緩いカーブと沿道の建物。
- [エージェント向け手順](docs/AGENT_WORKFLOW.md)
- [要求・計画の形式](docs/SCENE_FORMAT.md)
- [接続方式とコスト](docs/TOOL_DESIGN.md)
- [検証記録](docs/VALIDATION.md)

## 開発

街を生成するだけなら、この節の作業は不要です。要求JSONを編集して `city.py` を実行してください。
ここからは、道路のルールや生成器そのものを変更する開発者向けです。

道路の計画・形状計算・制約検証は `road_authoring/src/` のTypeScriptファイル4つに実装されています。

実行時には、TypeScriptをJavaScriptへ変換した `city_generator/road_runtime/` のファイルをNode.jsで読み込みます。
変換済みファイルも配布するため、通常利用ではTypeScriptのインストールや変換作業は不要です。
元ソースと変換済みファイルの食い違いを検出するため、実行前に元ソースのハッシュ（内容の識別値）を確認します。

`road_authoring/src/` を変更した場合だけ、TypeScriptコンパイラーの実行ファイルを `CITY_TSC` に指定し、変換済みファイルを更新してください。
現在の変換スクリプトはTypeScript 7系の `--ignoreConfig` オプションを使います（7.0.2で検証）。

```sh
CITY_TSC=/path/to/tsc node city_generator/compile_roads.mjs
```

変更後は、街の計画と道路生成の自動テストを実行します。以下はBlenderで画像を描画するコマンドではありません。

```sh
python3 -m unittest discover -s city_generator/tests -v
python3 -m unittest discover -s road_generator/tests -v
```

## 紹介画像について

街の画像は、本プロジェクトで生成したBlenderシーンをUnreal Engineでレンダリングしたものです。
アセットのクローズアップはBlender EEVEEでレンダリングしています。
公開範囲はBlenderでの都市シーン生成までで、Unreal Engineのレンダリング処理は含みません。

## ライセンス

本プロジェクトのコードは [MIT License](LICENSE) で公開しています。
フォントや依存ソフトには、それぞれのライセンスが適用されます。詳細は [依存とライセンス](docs/PROVENANCE.md) を参照してください。
