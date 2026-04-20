"""
blur_faces.py
手動でぼかし範囲を指定できる画像編集GUIアプリケーション

使い方:
  1. 「画像を選択」ボタンで画像ファイルを開く
  2. 画像上でマウスをドラッグしてぼかしたい領域を選択
  3. 「確定」ボタン（またはEnterキー）でガウシアンぼかしを適用
  4. 複数の領域を続けて選択・確定できる
  5. 「保存」ボタンで上書き保存、「別名保存」で別ファイルに保存

必要ライブラリ:
  pip install opencv-python pillow
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import numpy as np
from PIL import Image, ImageTk
import os


# ──────────────────────────────────────────────
# 定数
# ──────────────────────────────────────────────
DISPLAY_MAX_W = 1200   # 表示ウィンドウの最大幅
DISPLAY_MAX_H = 800    # 表示ウィンドウの最大高さ
SAVE_MAX_W    = 1200   # 保存時の最大幅（元解像度がこれ以下なら維持）
BLUR_KERNEL   = 51     # ガウシアンぼかしのカーネルサイズ（奇数）
RECT_COLOR    = "#FF4444"   # ドラッグ中の矩形色
DONE_COLOR    = "#44BBFF"   # 確定済み矩形色


# ──────────────────────────────────────────────
# ランチャーウィンドウ
# ──────────────────────────────────────────────
class LauncherApp:
    """起動時に表示される「画像を選択」ウィンドウ"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Blur Tool – 画像ぼかしツール")
        self.root.resizable(False, False)
        self._build_ui()
        self._center_window(400, 260)

    def _build_ui(self):
        # 背景フレーム
        bg = tk.Frame(self.root, bg="#1a1a2e", padx=40, pady=40)
        bg.pack(fill="both", expand=True)

        # タイトル
        tk.Label(
            bg, text="🖼  Blur Tool",
            font=("Segoe UI", 20, "bold"),
            fg="#e0e0ff", bg="#1a1a2e"
        ).pack(pady=(0, 6))

        tk.Label(
            bg, text="画像を選択してぼかし範囲を指定できます",
            font=("Segoe UI", 10),
            fg="#9090b0", bg="#1a1a2e"
        ).pack(pady=(0, 24))

        # 選択ボタン
        btn = tk.Button(
            bg, text="📂  画像を選択",
            font=("Segoe UI", 12, "bold"),
            fg="white", bg="#5c6bc0",
            activebackground="#7986cb", activeforeground="white",
            relief="flat", padx=20, pady=10, cursor="hand2",
            command=self._open_image
        )
        btn.pack(fill="x")
        btn.bind("<Enter>", lambda e: btn.config(bg="#7986cb"))
        btn.bind("<Leave>", lambda e: btn.config(bg="#5c6bc0"))

        # 対応形式メモ
        tk.Label(
            bg, text="対応形式: JPG / PNG / BMP / GIF / WebP",
            font=("Segoe UI", 8),
            fg="#606080", bg="#1a1a2e"
        ).pack(pady=(16, 0))

    def _open_image(self):
        path = filedialog.askopenfilename(
            title="画像を選択",
            filetypes=[
                ("画像ファイル", "*.jpg *.jpeg *.png *.bmp *.gif *.webp"),
                ("すべてのファイル", "*.*"),
            ]
        )
        if not path:
            return
        # 編集ウィンドウを新しいトップレベルで開く
        editor_win = tk.Toplevel(self.root)
        BlurEditorApp(editor_win, path)

    def _center_window(self, w: int, h: int):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")


# ──────────────────────────────────────────────
# 編集ウィンドウ
# ──────────────────────────────────────────────
class BlurEditorApp:
    """画像を表示し、ぼかし範囲をマウスドラッグで指定するエディタ"""

    def __init__(self, win: tk.Toplevel, image_path: str):
        self.win = win
        self.image_path = image_path
        self.filename = os.path.basename(image_path)

        # ──── 画像の読み込み ────
        self.orig_cv = cv2.imdecode(
            np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if self.orig_cv is None:
            messagebox.showerror("エラー", f"画像を開けませんでした:\n{image_path}")
            win.destroy()
            return

        # 作業用コピー（ぼかしを蓄積していく）
        self.work_cv = self.orig_cv.copy()

        # ──── 表示スケールの計算 ────
        oh, ow = self.orig_cv.shape[:2]
        scale_w = DISPLAY_MAX_W / ow
        scale_h = DISPLAY_MAX_H / oh
        self.scale = min(1.0, scale_w, scale_h)   # 縮小のみ（拡大しない）
        self.disp_w = int(ow * self.scale)
        self.disp_h = int(oh * self.scale)

        # ──── 確定済み矩形リスト (原寸座標) ────
        self.confirmed_rects: list[tuple[int, int, int, int]] = []

        # ──── ドラッグ中の状態 ────
        self.drag_start: tuple[int, int] | None = None
        self.current_rect: tuple[int, int, int, int] | None = None  # (x1,y1,x2,y2) 表示座標

        # ──── UI 構築 ────
        self.win.title(f"Blur Tool – {self.filename}")
        self.win.configure(bg="#1a1a2e")
        self.win.resizable(True, True)
        self._build_ui()
        self._center_window()
        self._refresh_canvas()

        # キーバインド
        self.win.bind("<Return>",  self._on_enter)
        self.win.bind("<Escape>",  self._on_escape)
        self.win.bind("<Control-z>", self._on_undo)
        self.win.bind("<Control-s>", lambda e: self._save_overwrite())

    # ──────────────────────────
    # UI 構築
    # ──────────────────────────
    def _build_ui(self):
        # ── ツールバー ──
        toolbar = tk.Frame(self.win, bg="#12122a", pady=6)
        toolbar.pack(fill="x", side="top")

        btn_style = dict(
            font=("Segoe UI", 10, "bold"),
            relief="flat", padx=12, pady=6, cursor="hand2"
        )

        self.btn_confirm = tk.Button(
            toolbar, text="✅  確定  (Enter)",
            fg="white", bg="#43a047", activebackground="#66bb6a", activeforeground="white",
            command=self._confirm_region, **btn_style
        )
        self.btn_confirm.pack(side="left", padx=(10, 4))

        self.btn_undo = tk.Button(
            toolbar, text="↩  元に戻す  (Ctrl+Z)",
            fg="white", bg="#f57c00", activebackground="#fb8c00", activeforeground="white",
            command=self._undo, **btn_style
        )
        self.btn_undo.pack(side="left", padx=4)

        self.btn_clear = tk.Button(
            toolbar, text="🗑  すべてクリア",
            fg="white", bg="#c62828", activebackground="#e53935", activeforeground="white",
            command=self._clear_all, **btn_style
        )
        self.btn_clear.pack(side="left", padx=4)

        # 右側：保存ボタン群
        tk.Button(
            toolbar, text="💾  別名保存",
            fg="white", bg="#1565c0", activebackground="#1976d2", activeforeground="white",
            command=self._save_as, **btn_style
        ).pack(side="right", padx=(4, 10))

        tk.Button(
            toolbar, text="💾  上書き保存  (Ctrl+S)",
            fg="white", bg="#00695c", activebackground="#00897b", activeforeground="white",
            command=self._save_overwrite, **btn_style
        ).pack(side="right", padx=4)

        # ── ステータスバー ──
        self.status_var = tk.StringVar(value="ドラッグで範囲を選択 → Enter で確定")
        status_bar = tk.Label(
            self.win, textvariable=self.status_var,
            font=("Segoe UI", 9), fg="#9090b0", bg="#12122a",
            anchor="w", padx=10, pady=4
        )
        status_bar.pack(fill="x", side="bottom")

        # ── キャンバス（スクロール対応） ──
        canvas_frame = tk.Frame(self.win, bg="#1a1a2e")
        canvas_frame.pack(fill="both", expand=True)

        h_scroll = tk.Scrollbar(canvas_frame, orient="horizontal", bg="#1a1a2e")
        h_scroll.pack(side="bottom", fill="x")
        v_scroll = tk.Scrollbar(canvas_frame, orient="vertical", bg="#1a1a2e")
        v_scroll.pack(side="right", fill="y")

        self.canvas = tk.Canvas(
            canvas_frame,
            width=self.disp_w, height=self.disp_h,
            bg="#0d0d1a", cursor="crosshair",
            highlightthickness=0,
            xscrollcommand=h_scroll.set,
            yscrollcommand=v_scroll.set,
            scrollregion=(0, 0, self.disp_w, self.disp_h)
        )
        self.canvas.pack(fill="both", expand=True)
        h_scroll.config(command=self.canvas.xview)
        v_scroll.config(command=self.canvas.yview)

        # マウスイベント
        self.canvas.bind("<ButtonPress-1>",   self._on_mouse_down)
        self.canvas.bind("<B1-Motion>",        self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>",  self._on_mouse_up)

        # ホバーエフェクト用
        def _hover(btn, color_on, color_off):
            btn.bind("<Enter>", lambda e: btn.config(bg=color_on))
            btn.bind("<Leave>", lambda e: btn.config(bg=color_off))

        _hover(self.btn_confirm, "#66bb6a", "#43a047")
        _hover(self.btn_undo,   "#fb8c00", "#f57c00")
        _hover(self.btn_clear,  "#e53935", "#c62828")

    # ──────────────────────────
    # ウィンドウ中央配置
    # ──────────────────────────
    def _center_window(self):
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        w = min(self.disp_w + 20, sw - 40)
        h = min(self.disp_h + 100, sh - 80)
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    # ──────────────────────────
    # キャンバス描画
    # ──────────────────────────
    def _refresh_canvas(self):
        """work_cv を表示サイズにリサイズしてキャンバスに描画（確定済み楕円を青枠で表示）"""
        disp_img = cv2.resize(
            self.work_cv, (self.disp_w, self.disp_h),
            interpolation=cv2.INTER_AREA
        )
        # 確定済み領域を楕円の青枠で可視化
        for (x1, y1, x2, y2) in self.confirmed_rects:
            dx1 = int(x1 * self.scale)
            dy1 = int(y1 * self.scale)
            dx2 = int(x2 * self.scale)
            dy2 = int(y2 * self.scale)
            cx = (dx1 + dx2) // 2
            cy = (dy1 + dy2) // 2
            axes = ((dx2 - dx1) // 2, (dy2 - dy1) // 2)
            cv2.ellipse(disp_img, (cx, cy), axes, 0, 0, 360, (255, 180, 0), 2)

        rgb = cv2.cvtColor(disp_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        self._tk_img = ImageTk.PhotoImage(pil_img)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)
        self.canvas.config(scrollregion=(0, 0, self.disp_w, self.disp_h))

    def _draw_selection_rect(self):
        """ドラッグ中の赤い選択矩形を描画"""
        self.canvas.delete("sel_rect")
        if self.current_rect:
            x1, y1, x2, y2 = self.current_rect
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline=RECT_COLOR, width=2, dash=(6, 3),
                tag="sel_rect"
            )

    # ──────────────────────────
    # マウスイベント
    # ──────────────────────────
    def _canvas_coords(self, event) -> tuple[int, int]:
        """スクロールを考慮したキャンバス座標を返す"""
        x = int(self.canvas.canvasx(event.x))
        y = int(self.canvas.canvasy(event.y))
        return x, y

    def _on_mouse_down(self, event):
        x, y = self._canvas_coords(event)
        self.drag_start = (x, y)
        self.current_rect = None
        self.status_var.set("ドラッグして範囲を選択中…")

    def _on_mouse_drag(self, event):
        if self.drag_start is None:
            return
        x, y = self._canvas_coords(event)
        sx, sy = self.drag_start
        # 画像範囲内にクランプ
        x = max(0, min(x, self.disp_w))
        y = max(0, min(y, self.disp_h))
        self.current_rect = (min(sx, x), min(sy, y), max(sx, x), max(sy, y))
        self._draw_selection_rect()

    def _on_mouse_up(self, event):
        if self.drag_start is None:
            return
        x, y = self._canvas_coords(event)
        sx, sy = self.drag_start
        x = max(0, min(x, self.disp_w))
        y = max(0, min(y, self.disp_h))
        x1, y1 = min(sx, x), min(sy, y)
        x2, y2 = max(sx, x), max(sy, y)
        if (x2 - x1) < 4 or (y2 - y1) < 4:
            self.current_rect = None
            self.status_var.set("範囲が小さすぎます。もう一度ドラッグしてください。")
            return
        self.current_rect = (x1, y1, x2, y2)
        w = x2 - x1
        h = y2 - y1
        self.status_var.set(
            f"選択中: ({x1}, {y1}) – ({x2}, {y2})  [{w}×{h}px 表示]  "
            f"→ Enter で確定 / 再ドラッグでやり直し"
        )

    # ──────────────────────────
    # ぼかし操作
    # ──────────────────────────
    def _apply_ellipse_blur(self, img: np.ndarray, ox1: int, oy1: int, ox2: int, oy2: int):
        """
        img の (ox1,oy1)-(ox2,oy2) の矩形内にぴったり収まる楕円だけを
        ガウシアンぼかしし、楕円外（四隅）は元のピクセルを維持する。
        """
        roi = img[oy1:oy2, ox1:ox2]
        rh, rw = roi.shape[:2]

        # カーネルサイズ（奇数保証）
        ksize = max(BLUR_KERNEL, (max(rw, rh) // 5) | 1)
        blurred_roi = cv2.GaussianBlur(roi, (ksize, ksize), 0)

        # 楕円マスク（白=ぼかし領域、黒=元画像領域）
        mask = np.zeros((rh, rw), dtype=np.uint8)
        cx, cy = rw // 2, rh // 2
        cv2.ellipse(mask, (cx, cy), (rw // 2, rh // 2), 0, 0, 360, 255, -1)

        # マスクを 3ch に拡張して合成
        mask3 = cv2.merge([mask, mask, mask])
        combined = np.where(mask3 == 255, blurred_roi, roi)
        img[oy1:oy2, ox1:ox2] = combined

    def _confirm_region(self):
        """現在の選択範囲（楕円）にガウシアンぼかしを適用して確定"""
        if self.current_rect is None:
            self.status_var.set("⚠ 先にドラッグで範囲を選択してください。")
            return

        dx1, dy1, dx2, dy2 = self.current_rect
        # 表示座標 → 原寸座標
        ox1 = int(dx1 / self.scale)
        oy1 = int(dy1 / self.scale)
        ox2 = int(dx2 / self.scale)
        oy2 = int(dy2 / self.scale)
        # 画像範囲内にクランプ
        h, w = self.work_cv.shape[:2]
        ox1, oy1 = max(0, ox1), max(0, oy1)
        ox2, oy2 = min(w, ox2), min(h, oy2)

        if (ox2 - ox1) < 2 or (oy2 - oy1) < 2:
            self.status_var.set("⚠ 範囲が小さすぎます。")
            return

        # 楕円ぼかし適用
        self._apply_ellipse_blur(self.work_cv, ox1, oy1, ox2, oy2)

        # 確定済みリストに追加
        self.confirmed_rects.append((ox1, oy1, ox2, oy2))

        self.current_rect = None
        self.drag_start = None
        self._refresh_canvas()
        self.canvas.delete("sel_rect")
        n = len(self.confirmed_rects)
        self.status_var.set(
            f"✅ ぼかし（楕円）を適用しました（計 {n} 箇所）。続けて範囲を選択するか「保存」してください。"
        )

    def _on_enter(self, event):
        self._confirm_region()

    def _on_escape(self, event):
        """選択をキャンセル"""
        self.current_rect = None
        self.drag_start = None
        self.canvas.delete("sel_rect")
        self.status_var.set("選択をキャンセルしました。")

    def _undo(self, _event=None):
        """最後に確定したぼかしを1件取り消す"""
        if not self.confirmed_rects:
            self.status_var.set("⚠ 取り消せる操作がありません。")
            return
        self.confirmed_rects.pop()
        # work_cv を orig から再構築（楕円ぼかしを再適用）
        self.work_cv = self.orig_cv.copy()
        for (ox1, oy1, ox2, oy2) in self.confirmed_rects:
            self._apply_ellipse_blur(self.work_cv, ox1, oy1, ox2, oy2)
        self._refresh_canvas()
        n = len(self.confirmed_rects)
        self.status_var.set(f"↩ 1件取り消しました（残り {n} 箇所）。")

    def _clear_all(self):
        """すべてのぼかしを取り消す"""
        if not self.confirmed_rects:
            self.status_var.set("⚠ クリアできる操作がありません。")
            return
        if not messagebox.askyesno("確認", "すべてのぼかしをリセットしますか？"):
            return
        self.confirmed_rects.clear()
        self.work_cv = self.orig_cv.copy()
        self.current_rect = None
        self._refresh_canvas()
        self.canvas.delete("sel_rect")
        self.status_var.set("🗑 すべてのぼかしをリセットしました。")

    # ──────────────────────────
    # 保存
    # ──────────────────────────
    def _prepare_save_image(self) -> np.ndarray:
        """
        保存用画像を返す。
        横幅が SAVE_MAX_W を超える場合はリサイズ（縦横比維持）。
        それ以下の場合は元解像度を維持。
        """
        h, w = self.work_cv.shape[:2]
        if w > SAVE_MAX_W:
            new_h = int(h * SAVE_MAX_W / w)
            return cv2.resize(self.work_cv, (SAVE_MAX_W, new_h), interpolation=cv2.INTER_LANCZOS4)
        return self.work_cv.copy()

    def _save_to_path(self, path: str):
        """指定パスに保存"""
        img = self._prepare_save_image()
        ext = os.path.splitext(path)[1].lower()
        # encode → fromfileで日本語パス対応
        success, buf = cv2.imencode(ext if ext else ".jpg", img)
        if not success:
            messagebox.showerror("エラー", "画像のエンコードに失敗しました。")
            return
        with open(path, "wb") as f:
            f.write(buf.tobytes())
        self.status_var.set(f"💾 保存完了: {path}")
        messagebox.showinfo("保存完了", f"画像を保存しました:\n{path}")

    def _save_overwrite(self):
        """元のファイルに上書き保存"""
        if not self.confirmed_rects:
            messagebox.showwarning("確認", "まだぼかしが適用されていません。")
            return
        if messagebox.askyesno("上書き保存", f"元のファイルを上書きしますか？\n{self.image_path}"):
            self._save_to_path(self.image_path)

    def _save_as(self):
        """別名で保存"""
        if not self.confirmed_rects:
            if not messagebox.askyesno("確認", "ぼかしが適用されていません。それでも保存しますか？"):
                return
        base, ext = os.path.splitext(self.filename)
        init_name = f"{base}_blurred{ext}"
        path = filedialog.asksaveasfilename(
            title="別名で保存",
            initialfile=init_name,
            initialdir=os.path.dirname(self.image_path),
            defaultextension=ext or ".jpg",
            filetypes=[
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG",  "*.png"),
                ("BMP",  "*.bmp"),
                ("すべてのファイル", "*.*"),
            ]
        )
        if path:
            self._save_to_path(path)


# ──────────────────────────────────────────────
# エントリポイント
# ──────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = LauncherApp(root)
    root.mainloop()
