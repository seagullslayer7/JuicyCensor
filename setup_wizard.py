from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QComboBox, QCheckBox,
                               QPlainTextEdit, QPushButton, QProgressBar, QMessageBox)
from bootstrap import Installer


class InstallThread(QThread):
    message = Signal(str)
    completed = Signal(bool, str)
    def __init__(self, root, profile, models, parent):
        super().__init__(parent)
        self.installer = Installer(root, self.message.emit)
        self.profile, self.models = profile, models
    def run(self):
        try:
            self.installer.install(self.profile, self.models)
            self.completed.emit(True, '')
        except Exception as exc:
            self.completed.emit(False, str(exc))


class SetupWizard(QDialog):
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root, self.thread = Path(root), None
        self.setWindowTitle('JuicyCensor 2.0 · First-run setup')
        self.resize(700, 590)
        layout = QVBoxLayout(self)
        title = QLabel('Let’s get JuicyCensor ready')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)
        note = QLabel('Download a private Python environment, verified processing packages, FFmpeg and the Vulkan runtime. Nothing is added to your system Python or PATH.\n\nAllow several GB of free space. NVIDIA needs the larger CUDA download. Starter models add download time; you can skip them and download models when needed.\n\nKeep your GPU driver up to date using NVIDIA, AMD or Intel’s own installer. A separate CUDA Toolkit or Visual Studio is not required.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.profile = QComboBox()
        self.profile.addItem('AMD / Intel / CPU · smaller download', 'cpu')
        self.profile.addItem('NVIDIA CUDA · accelerated speech analysis', 'cuda')
        self.profile.setToolTip('Both profiles support hardware video export. CUDA adds NVIDIA-accelerated speech analysis.')
        layout.addWidget(self.profile)
        self.models = QCheckBox('Download starter English models now (recommended)')
        self.models.setChecked(True)
        layout.addWidget(self.models)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        layout.addWidget(self.log, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.install_button = QPushButton('Download and set up')
        self.install_button.setProperty('primary', True)
        self.install_button.clicked.connect(self.start)
        layout.addWidget(self.install_button)
        self.cancel_button = QPushButton('Not now')
        self.cancel_button.clicked.connect(self.cancel)
        layout.addWidget(self.cancel_button)
    def append(self, line):
        self.log.appendPlainText(line)
        path = self.root / 'logs/setup.log'
        path.parent.mkdir(exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
            f.write(line + '\n')
    def start(self):
        self.thread = InstallThread(self.root, self.profile.currentData(), self.models.isChecked(), self)
        self.thread.message.connect(self.append)
        self.thread.completed.connect(self.done_install)
        self.install_button.setEnabled(False)
        self.profile.setEnabled(False)
        self.models.setEnabled(False)
        self.cancel_button.setText('Cancel setup')
        self.progress.setRange(0, 0)
        self.thread.start()
    def done_install(self, success, error):
        self.thread.wait()
        self.thread = None
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if success else 0)
        if success:
            self.accept()
        else:
            self.append(error)
            self.install_button.setText('Retry setup')
            self.install_button.setEnabled(True)
            self.profile.setEnabled(True)
            self.models.setEnabled(True)
            self.cancel_button.setText('Close')
            self.cancel_button.setEnabled(True)
    def cancel(self):
        if self.thread:
            self.thread.installer.cancel()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText('Stopping…')
        else:
            self.reject()
    def reject(self):
        if self.thread:
            self.cancel()
        else:
            super().reject()
    def closeEvent(self, event):
        if self.thread:
            self.cancel()
            event.ignore()
        else:
            event.accept()
