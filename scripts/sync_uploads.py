"""
根据 stickerpicker/packs/*.json（排除 index.json）来同步 backup/uploads 文件内容。

逻辑变更：
1) 从所有包 JSON 中收集媒体 ID 集合（含每个 sticker 的 `stickers.id` 与
	`stickers.info.thumbnail_url` 两类 ID）。
2) 如果 backup/uploads 中某一行对应的媒体 ID 不在该集合中：
	- 先将该条目的 `purpose` 设为 `none`（仅在输出文件/日志中体现），
	- 然后从 uploads 文件（即 backup/uploads）中删除对应的行。

为了便于后续处理，被移除条目的「purpose=none」会被写入一个旁路 NDJSON 文件
backup/uploads_purpose_none.ndjson（可通过参数自定义），以便进一步外部使用。
"""

import os
import argparse
import json
from typing import Set, List, Tuple, Dict, Any
from keep_mmr import set_media_purpose


def _default_paths() -> tuple[str, str, str]:
	"""返回默认的 uploads 文件、packs 目录路径与 purpose 输出文件路径。"""
	root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
	uploads_path = os.path.join(root_dir, "backup", "uploads")
	packs_dir = os.path.join(root_dir, "stickerpicker", "packs")
	purpose_out = os.path.join(root_dir, "backup", "uploads_purpose_none.ndjson")
	return uploads_path, packs_dir, purpose_out


def _extract_media_id_from_url(url: str) -> str:
	"""从 mxc://server/<media_id> 或包含斜杠的字符串中提取最后一段作为 media_id。"""
	return url.rsplit("/", 1)[-1]


def collect_media_ids_from_packs(packs_dir: str, verbose: bool = False) -> Set[str]:
	"""
	遍历 packs 目录下的所有 json 文件（排除 index.json），
	收集 stickers.id 与 stickers.info.thumbnail_url 中的 media_id。
	"""
	if not os.path.isdir(packs_dir):
		raise FileNotFoundError(f"packs 目录不存在: {packs_dir}")

	present: Set[str] = set()
	for name in os.listdir(packs_dir):
		if not name.endswith(".json"):
			continue
		if name == "index.json":
			continue
		path = os.path.join(packs_dir, name)
		if not os.path.isfile(path):
			continue
		try:
			with open(path, "r", encoding="utf-8") as f:
				data = json.load(f)
		except Exception as e:
			if verbose:
				print(f"[warn] 读取包失败: {path}: {e}")
			continue

		stickers = data.get("stickers")
		if not isinstance(stickers, list):
			continue
		for s in stickers:
			if not isinstance(s, dict):
				continue
			sid = s.get("id")
			if isinstance(sid, str):
				present.add(_extract_media_id_from_url(sid))
			info = s.get("info")
			if isinstance(info, dict):
				thumb = info.get("thumbnail_url")
				if isinstance(thumb, str):
					present.add(_extract_media_id_from_url(thumb))
	return present


def _ensure_parent_dir(path: str) -> None:
	d = os.path.dirname(path)
	if d and not os.path.isdir(d):
		os.makedirs(d, exist_ok=True)


def read_uploads_lines(path: str) -> List[str]:
	"""读取 uploads 文件的所有行（逐行 JSON）。"""
	if not os.path.isfile(path):
		raise FileNotFoundError(f"uploads 文件不存在: {path}")
	with open(path, "r", encoding="utf-8") as f:
		return f.read().splitlines()


def filter_uploads_lines(
	lines: List[str], present_media_ids: Set[str], verbose: bool = False
) -> Tuple[List[str], List[Dict[str, Any]]]:
	"""
	- 保留其中 url 的 media_id 存在于 present_media_ids 集合中的行。
	- 对于不存在的媒体：准备一份 purpose=none 的对象放入 removed 列表，并从输出中删除该行。
	- 对于无法解析的行（非 JSON 或缺少 url 字段），默认保留，并在 verbose 模式下打印警告。

	返回: (保留行的文本列表, 被移除条目的对象列表[已设置 purpose=none])
	"""
	kept: List[str] = []
	removed_objs: List[Dict[str, Any]] = []
	for ln in lines:
		ln_stripped = ln.strip()
		if ln_stripped == "":
			kept.append(ln)
			continue
		try:
			obj = json.loads(ln_stripped)
			url = obj.get("url")
			if not isinstance(url, str):
				if verbose:
					print("[warn] 行缺少有效 url 字段，保留原样:", ln)
				kept.append(ln)
				continue
			media_id = _extract_media_id_from_url(url)
			if media_id in present_media_ids:
				kept.append(ln)
			else:
				# 标记 purpose=none，并记录到移除清单
				obj["purpose"] = "none"
				removed_objs.append(obj)
				if verbose:
					print(f"移除缺失媒体: media_id={media_id}")
		except json.JSONDecodeError:
			if verbose:
				print("[warn] 行不是有效 JSON，保留原样:", ln)
			kept.append(ln)
	return kept, removed_objs


def write_uploads_lines(path: str, lines: List[str]) -> None:
	"""将过滤后的行写回 uploads 文件。"""
	content = "\n".join(lines)
	# 确保以换行结束，保持与原文件风格一致
	if not content.endswith("\n"):
		content += "\n"
	with open(path, "w", encoding="utf-8") as f:
		f.write(content)


def main() -> int:
	uploads_default, packs_default, purpose_out_default = _default_paths()

	parser = argparse.ArgumentParser(description="根据 packs JSON 同步 backup/uploads，移除不存在的媒体条目并标记 purpose=none")
	parser.add_argument("token", help="Matrix 管理 API 的 access token，用于调用 set_media_purpose")
	parser.add_argument("--uploads-file", default=uploads_default, help="uploads 文件路径 (默认: backup/uploads)")
	parser.add_argument("--packs-dir", default=packs_default, help="sticker 包目录 (默认: stickerpicker/packs)")
	parser.add_argument("--server", default="mtx01.cc", help="媒体服务器名（例如: mtx01.cc），用于 set_media_purpose 调用")
	parser.add_argument("--dry-run", action="store_true", help="仅预览将要移除的条目，不写回文件")
	parser.add_argument("--verbose", "-v", action="store_true", help="打印详细处理信息")
	args = parser.parse_args()

	present_ids = collect_media_ids_from_packs(args.packs_dir, verbose=args.verbose)
	if args.verbose:
		print(f"从 packs 收集到媒体 ID 数量: {len(present_ids)}")

	lines = read_uploads_lines(args.uploads_file)

	before = len(lines)
	filtered, removed_objs = filter_uploads_lines(lines, present_ids, verbose=args.verbose)
	after = len(filtered)
	removed_count = len(removed_objs)

	if args.verbose:
		print(f"uploads 总行数: {before}，保留: {after}，移除: {removed_count}")

	if args.dry_run:
		if removed_count:
			print(f"预览：将标记 purpose=none 并移除 {removed_count} 条条目；不会实际写入 uploads 或调用 API")
		else:
			print("预览：无需要移除的条目")
		return 0

	if removed_count > 0:
		# 调用 keep_mmr.set_media_purpose 将目的设置为 none
		ok = 0
		fail = 0
		for obj in removed_objs:
			url = obj.get("url")
			if not isinstance(url, str):
				fail += 1
				if args.verbose:
					print("[warn] 移除对象缺少 url 字段，跳过 purpose 设置:", obj)
				continue
			media_id = _extract_media_id_from_url(url)
			result = set_media_purpose(token=args.token, server=args.server, media_id=media_id, purpose="none")
			if 200 <= result.status < 300:
				ok += 1
				if args.verbose:
					print(f"已设置 purpose=none: {media_id} (status={result.status})")
			else:
				fail += 1
				print(f"[error] 设置 purpose=none 失败: {media_id} (status={result.status})")
				if result.body:
					try:
						parsed = json.loads(result.body)
						print(json.dumps(parsed, ensure_ascii=False, indent=2))
					except Exception:
						print(result.body)
		print(f"purpose 设置完成：成功 {ok}，失败 {fail}")

		# 写回过滤后的 uploads
		write_uploads_lines(args.uploads_file, filtered)
		print(f"同步完成：已标记 purpose=none 并移除 {removed_count} 条条目")
	else:
		print("同步完成：无需要移除的条目")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())

