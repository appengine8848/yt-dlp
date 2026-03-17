import sys
import os
import re
import yt_dlp
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLineEdit, QPushButton, QTextEdit, 
                               QLabel, QFrame, QProgressBar, QGraphicsDropShadowEffect,
                               QComboBox, QCheckBox, QFormLayout, QFileDialog, QSpinBox)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QColor

# 工具函数：剔除 ANSI 颜色乱码
def clean_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class DownloadWorker(QThread):
    progress_signal = Signal(dict)
    log_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, url, options):
        super().__init__()
        self.url = url
        self.options = options
        self._is_cancelled = False

    def run(self):
        def progress_hook(d):
            if self._is_cancelled: raise Exception("USER_CANCELLED")
            self.progress_signal.emit(d)
        
        class Logger:
            def __init__(self, signal): self.signal = signal
            def debug(self, msg): self.signal.emit(clean_ansi(msg))
            def info(self, msg): self.signal.emit(clean_ansi(msg))
            def warning(self, msg): self.signal.emit(clean_ansi(msg))
            def error(self, msg): self.signal.emit(clean_ansi(msg))

        self.options['progress_hooks'] = [progress_hook]
        self.options['logger'] = Logger(self.log_signal)
        
        try:
            with yt_dlp.YoutubeDL(self.options) as ydl:
                ydl.download([self.url])
            if not self._is_cancelled: self.finished_signal.emit(True)
        except Exception as e:
            err_msg = str(e)
            if "USER_CANCELLED" in err_msg: 
                self.log_signal.emit("\n[提示] 任务已手动停止。")
            elif "ffmpeg" in err_msg.lower():
                self.log_signal.emit("\n[致命错误] FFmpeg 调用失败！请确保 ffmpeg.exe 在程序同目录下。")
            else: 
                self.log_signal.emit(f"\n[错误] {err_msg}")
            self.finished_signal.emit(False)

    def stop(self):
        self._is_cancelled = True

class FinalProBeautyDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YT-DLP 视频下载 Pro")
        self.setFixedSize(600, 750)
        
        # 确定程序基础路径（兼容脚本和打包后的exe）
        if getattr(sys, 'frozen', False):
            self.base_path = os.path.dirname(sys.executable)
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))
        
        os.chdir(self.base_path)
        self.worker = None
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #F8FAFC; }
            QWidget#MainCard { background-color: #FFFFFF; border-radius: 12px; }
            QLabel { color: #475569; font-weight: 600; font-family: 'Segoe UI', 'Microsoft YaHei'; }
            QLineEdit, QSpinBox, QComboBox { 
                background-color: #F1F5F9; border: 1px solid #E2E8F0; 
                border-radius: 6px; padding: 8px; color: #1E293B;
            }
            QLineEdit:focus { border: 1px solid #3B82F6; background-color: #FFFFFF; }
            QPushButton#ActionBtn { 
                background-color: #3B82F6; color: white; border-radius: 8px; 
                font-weight: bold; font-size: 15px; border: none;
            }
            QPushButton#ActionBtn:hover { background-color: #2563EB; }
            QPushButton#StopBtn { 
                background-color: #EF4444; color: white; border-radius: 8px; 
                font-weight: bold; font-size: 15px; border: none;
            }
            QPushButton#SubBtn { background-color: #E2E8F0; color: #475569; border-radius: 4px; border: 1px solid #CBD5E1; }
            QProgressBar { border: none; background-color: #F1F5F9; border-radius: 4px; text-align: center; height: 12px; }
            QProgressBar::chunk { background-color: #10B981; border-radius: 4px; }
            QTextEdit { background-color: #0F172A; color: #E2E8F0; border-radius: 8px; font-family: 'Consolas'; font-size: 11px; padding: 8px; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)

        self.card = QFrame()
        self.card.setObjectName("MainCard")
        card_layout = QVBoxLayout(self.card)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20); shadow.setYOffset(5); shadow.setColor(QColor(0,0,0,30))
        self.card.setGraphicsEffect(shadow)

        # 1. URL
        card_layout.addWidget(QLabel("视频或播放列表地址"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴 Bilibili/Youtube URL...")
        card_layout.addWidget(self.url_input)

        # 2. 设置区
        settings_frame = QFrame()
        settings_layout = QHBoxLayout(settings_frame)
        
        left_form = QFormLayout()
        self.res_combo = QComboBox()
        self.res_combo.addItems(["1080", "2160", "1440", "720", "480"])
        self.format_combo = QComboBox()
        self.format_combo.addItems(["mp4", "mkv", "webm", "mp3"])
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 32); self.thread_spin.setValue(8)
        left_form.addRow("分辨率:", self.res_combo)
        left_form.addRow("保存格式:", self.format_combo)
        left_form.addRow("并行线程:", self.thread_spin)
        
        right_form = QFormLayout()
        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("127.0.0.1:1080")
        self.cookie_path = QLineEdit()
        btn_cookie = QPushButton("...")
        btn_cookie.setObjectName("SubBtn")
        btn_cookie.setFixedWidth(40)
        btn_cookie.clicked.connect(self.select_cookie)
        cookie_lay = QHBoxLayout(); cookie_lay.addWidget(self.cookie_path); cookie_lay.addWidget(btn_cookie)
        right_form.addRow("代理:", self.proxy_input)
        right_form.addRow("Cookie:", cookie_lay)
        
        settings_layout.addLayout(left_form); settings_layout.addLayout(right_form)
        card_layout.addWidget(settings_frame)

        # 3. 功能开关
        switch_lay = QHBoxLayout()
        self.check_embed = QCheckBox("内嵌字幕"); self.check_embed.setChecked(True)
        self.check_thumb = QCheckBox("写入封面"); self.check_thumb.setChecked(True)
        self.check_metadata = QCheckBox("元数据"); self.check_metadata.setChecked(True)
        switch_lay.addWidget(self.check_embed); switch_lay.addWidget(self.check_thumb); switch_lay.addWidget(self.check_metadata)
        card_layout.addLayout(switch_lay)

        # 4. 进度显示
        self.status_label = QLabel("等待指令")
        self.progress_bar = QProgressBar()
        card_layout.addWidget(self.status_label)
        card_layout.addWidget(self.progress_bar)

        # 5. 控制按钮
        btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("开始下载")
        self.btn_run.setObjectName("ActionBtn")
        self.btn_run.setFixedHeight(45)
        self.btn_run.clicked.connect(self.start_task)
        
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setObjectName("StopBtn")
        self.btn_stop.setFixedHeight(45)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_task)
        
        btn_layout.addWidget(self.btn_run, 3); btn_layout.addWidget(self.btn_stop, 1)
        card_layout.addLayout(btn_layout)

        # 6. 日志
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        card_layout.addWidget(self.log_box)

        layout.addWidget(self.card)

    def select_cookie(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择Cookie文件", "", "Text Files (*.txt)")
        if f: self.cookie_path.setText(f)

    def update_progress(self, d):
        if d['status'] == 'downloading':
            p_raw = d.get('_percent_str', '0%')
            p_str = clean_ansi(p_raw).replace('%','').strip()
            try: self.progress_bar.setValue(int(float(p_str)))
            except: pass
            speed = clean_ansi(d.get('_speed_str','N/A'))
            self.status_label.setText(f"下载中 | 速度: {speed}")
        elif d['status'] == 'finished':
            self.status_label.setText("下载完成，FFmpeg 正在合并/转换...")

    def stop_task(self):
        if self.worker:
            self.worker.stop()
            self.btn_stop.setEnabled(False)

    def start_task(self):
        url = self.url_input.text().strip()
        if not url: return

        # 核心配置：手动指定 ffmpeg 路径
        # 这里指定的是文件夹路径，yt-dlp 会在里面寻找 ffmpeg.exe
        ffmpeg_dir = self.base_path 
        
        fmt_choice = self.format_combo.currentText()
        res_limit = self.res_combo.currentText()

        opts = {
            'ffmpeg_location': ffmpeg_dir,
            'outtmpl': os.path.join(self.base_path, '%(title)s.%(ext)s'),
            'concurrent_fragment_downloads': self.thread_spin.value(),
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'no_warnings': False,
        }

        if fmt_choice == "mp3":
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            # 兼容B站的最佳写法：抓取最佳视频+最佳音频，之后由 ffmpeg 合并
            opts['format'] = f"bestvideo[height<={res_limit}]+bestaudio/best[height<={res_limit}]/best"
            opts['merge_output_format'] = fmt_choice

        # 处理后处理器
        pps = opts.get('postprocessors', [])
        if self.check_thumb.isChecked():
            pps.append({'key': 'EmbedThumbnail'})
        if self.check_metadata.isChecked():
            pps.append({'key': 'FFmpegMetadata'})
        if self.check_embed.isChecked() and fmt_choice != "mp3":
            opts.update({'writesubtitles': True, 'writeautomaticsub': True})
            pps.append({'key': 'FFmpegEmbedSubtitle'})
        
        opts['postprocessors'] = pps

        if self.proxy_input.text(): opts['proxy'] = self.proxy_input.text()
        if self.cookie_path.text(): opts['cookiefile'] = self.cookie_path.text()

        self.log_box.clear()
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)
        
        self.worker = DownloadWorker(url, opts)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.log_signal.connect(self.log_box.append)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def on_finished(self, success):
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if success:
            self.status_label.setText("任务圆满完成！")
            self.progress_bar.setValue(100)
        else:
            self.status_label.setText("任务失败或被拦截")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FinalProBeautyDownloader()
    window.show()
    sys.exit(app.exec())