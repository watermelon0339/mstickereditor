"""
根据 stickerpicker/packs/thumbnails 目录来同步 backup/uploads 文件内容
如果 backup/uploads 中有但 thumbnails 目录中没有的文件，则删除 uploads 中对应的行
"""

import os
import argparse
import json
from typing import Set, List


def _default_paths() -> tuple[str, str]:
	"""返回默认的 uploads 文件和 thumbnails 目录路径。"""
	root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
	uploads_path = os.path.join(root_dir, "backup", "uploads")
	thumbs_dir = os.path.join(root_dir, "stickerpicker", "packs", "thumbnails")
	return uploads_path, thumbs_dir


def list_thumbnails(thumbs_dir: str) -> Set[str]:
	"""列出 thumbnails 目录下的所有文件名（不含路径），作为媒体 id 集合。"""
	if not os.path.isdir(thumbs_dir):
		raise FileNotFoundError(f"thumbnails 目录不存在: {thumbs_dir}")
	return {
		name
		for name in os.listdir(thumbs_dir)
		if os.path.isfile(os.path.join(thumbs_dir, name))
	}


def _extract_media_id_from_url(url: str) -> str:
	"""从 mxc://server/<media_id> 或包含斜杠的字符串中提取最后一段作为 media_id。"""
	# 例如: mxc://mtx01.cc/abcdef -> 返回 abcdef
	return url.rsplit("/", 1)[-1]


def read_uploads_lines(path: str) -> List[str]:
	"""读取 uploads 文件的所有行（逐行 JSON）。"""
	if not os.path.isfile(path):
		raise FileNotFoundError(f"uploads 文件不存在: {path}")
	with open(path, "r", encoding="utf-8") as f:
		return f.read().splitlines()


def filter_uploads_lines(lines: List[str], present_media_ids: Set[str], verbose: bool = False) -> List[str]:
	"""
	保留其中 url 的 media_id 存在于 present_media_ids 集合中的行。
	对于无法解析的行（非 JSON 或缺少 url 字段），默认保留，并在 verbose 模式下打印警告。
	"""
	kept: List[str] = []
	for ln in lines:
		ln_stripped = ln.strip()
		if ln_stripped == "":
			# 保留空行以维持文件结构一致性
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
				if verbose:
					print(f"移除缺失媒体: media_id={media_id}")
		except json.JSONDecodeError:
			if verbose:
				print("[warn] 行不是有效 JSON，保留原样:", ln)
			kept.append(ln)
	return kept


def write_uploads_lines(path: str, lines: List[str]) -> None:
	"""将过滤后的行写回 uploads 文件。"""
	content = "\n".join(lines)
	# 确保以换行结束，保持与原文件风格一致
	if not content.endswith("\n"):
		content += "\n"
	with open(path, "w", encoding="utf-8") as f:
		f.write(content)


def main() -> int:
	uploads_default, thumbs_default = _default_paths()

	parser = argparse.ArgumentParser(description="根据 thumbnails 目录同步 backup/uploads，移除不存在的媒体条目")
	parser.add_argument("--uploads-file", default=uploads_default, help="uploads 文件路径 (默认: backup/uploads)")
	parser.add_argument("--thumbs-dir", default=thumbs_default, help="thumbnails 目录路径 (默认: stickerpicker/packs/thumbnails)")
	parser.add_argument("--dry-run", action="store_true", help="仅预览将要移除的条目，不写回文件")
	parser.add_argument("--verbose", "-v", action="store_true", help="打印详细处理信息")
	args = parser.parse_args()

	present_ids = list_thumbnails(args.thumbs_dir)
	lines = read_uploads_lines(args.uploads_file)

	before = len(lines)
	filtered = filter_uploads_lines(lines, present_ids, verbose=args.verbose)
	after = len(filtered)
	removed_count = before - after

	if args.verbose:
		print(f"uploads 总行数: {before}，保留: {after}，移除: {removed_count}")

	if args.dry_run:
		print(f"预览完成：将移除 {removed_count} 条缺失媒体条目")
		return 0

	if removed_count > 0:
		write_uploads_lines(args.uploads_file, filtered)
		print(f"同步完成：已移除 {removed_count} 条缺失媒体条目")
	else:
		print("同步完成：无需要移除的条目")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())

