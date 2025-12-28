"""
删除 stickerpicker/packs/thumbnails 目录中不再使用的缩略图文件。

- 扫描 `stickerpicker/packs/` 目录中的所有 pack.json 文件(除了 index.json)，以收集当前使用的缩略图文件名。
- 遍历 `stickerpicker/packs/thumbnails/` 目录中的所有文件。
- 如果某个文件不在使用的缩略图列表中，则将其删除。
"""

import os
import json
import argparse
from typing import Set, List


def _default_paths() -> tuple[str, str]:
	"""返回默认的 packs 和 thumbnails 目录路径。"""
	root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
	packs_dir = os.path.join(root_dir, "stickerpicker", "packs")
	thumbs_dir = os.path.join(packs_dir, "thumbnails")
	return packs_dir, thumbs_dir


def collect_used_thumbnails(packs_dir: str) -> Set[str]:
	"""
	扫描 packs_dir 下的所有 pack.json（排除 index.json），收集使用中的缩略图文件名。

	返回文件名集合（不含路径）。
	"""
	used: Set[str] = set()

	if not os.path.isdir(packs_dir):
		raise FileNotFoundError(f"packs 目录不存在: {packs_dir}")

	for name in os.listdir(packs_dir):
		if not name.endswith(".json"):
			continue
		if name == "index.json":
			continue

		path = os.path.join(packs_dir, name)
		try:
			with open(path, "r", encoding="utf-8") as f:
				data = json.load(f)
		except json.JSONDecodeError as e:
			raise ValueError(f"JSON 解析失败: {path}: {e}")

		stickers = data.get("stickers", [])
		for s in stickers:
			info = s.get("info", {})
			thumb_url = info.get("thumbnail_url")
			if not thumb_url or not isinstance(thumb_url, str):
				continue
			# 期望形如: mxc://server/<id>
			fname = thumb_url.rsplit("/", 1)[-1]
			if fname:
				used.add(fname)

	return used


def list_thumbnails(thumbs_dir: str) -> List[str]:
	"""列出 thumbnails 目录下的所有文件名（不含路径）。"""
	if not os.path.isdir(thumbs_dir):
		raise FileNotFoundError(f"thumbnails 目录不存在: {thumbs_dir}")
	return [name for name in os.listdir(thumbs_dir) if os.path.isfile(os.path.join(thumbs_dir, name))]


def remove_unused_thumbnails(thumbs_dir: str, used: Set[str], dry_run: bool = False, verbose: bool = False) -> int:
	"""
	删除不在 used 集合中的缩略图文件。
	返回删除的文件数量。
	"""
	all_thumbs = list_thumbnails(thumbs_dir)
	to_remove = [name for name in all_thumbs if name not in used]

	if verbose:
		print(f"检测到缩略图总数: {len(all_thumbs)}，使用中的缩略图: {len(used)}，待删除: {len(to_remove)}")

	removed = 0
	for name in to_remove:
		path = os.path.join(thumbs_dir, name)
		if dry_run:
			print(f"[dry-run] 将删除: {path}")
		else:
			try:
				os.remove(path)
				removed += 1
				if verbose:
					print(f"已删除: {path}")
			except OSError as e:
				print(f"删除失败: {path}: {e}")

	if verbose:
		action = "将删除" if dry_run else "已删除"
		print(f"{action}文件数: {len(to_remove)}")

	return removed if not dry_run else len(to_remove)


def main():
	packs_dir_default, thumbs_dir_default = _default_paths()

	parser = argparse.ArgumentParser(description="删除 stickerpicker/packs/thumbnails 中未使用的缩略图文件")
	parser.add_argument("--packs-dir", default=packs_dir_default, help="packs 目录路径 (默认: 工作区 stickerpicker/packs)")
	parser.add_argument("--thumbs-dir", default=thumbs_dir_default, help="thumbnails 目录路径 (默认: packs/thumbnails)")
	parser.add_argument("--dry-run", action="store_true", help="仅显示将要删除的文件，不实际删除")
	parser.add_argument("--verbose", "-v", action="store_true", help="打印详细信息")
	args = parser.parse_args()

	used = collect_used_thumbnails(args.packs_dir)
	removed = remove_unused_thumbnails(args.thumbs_dir, used, dry_run=args.dry_run, verbose=args.verbose)

	if args.dry_run:
		print(f"预览完成：将删除 {removed} 个未使用缩略图")
	else:
		print(f"清理完成：已删除 {removed} 个未使用缩略图")


if __name__ == "__main__":
	main()