
from PyQt5 import QtCore, QtGui, QtWidgets
from .GUIv2 import Ui_HARTAnalyzer
from PyQt5.QtWidgets import QFileDialog

import random

class HARTWindow(QtWidgets.QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_HARTAnalyzer()
        self.ui.setupUi(self)

        # --- Non-destructive removals (hide legacy widgets instead of deleting) ---
        to_hide = [
            getattr(self.ui, "port_name_group", None),
            getattr(self.ui, "port_settings_group", None),
            getattr(self.ui, "primary_master_radio", None),
            getattr(self.ui, "secondary_master_radio", None),
            getattr(self.ui, "burst_mode_checkbox", None),
            getattr(self.ui, "actionI_need_HART_modem_2", None),
            
            # --- NUMBER OF PREAMBLES ---
            # + Comment next line to SHOW Number of preambles in GUI
            # - Uncomment it      to HIDE Number of Preambles in GUI
            getattr(self.ui, "send_data_group", None)
        ]
        for w in to_hide:
          if isinstance(w, QtWidgets.QWidget):
            w.hide()
          elif isinstance(w, QtWidgets.QAction):
            w.setVisible(False)

        
        """
        Randomize numeber of preambles with function.
        You may use params:
            a: int
            b: int
            , where a and b is random range: [a, b]
        Default: a = 3, b = 16
        """
        self.randomizeNumberOfPreambles()

        # --- Add CONTROL + Frame Format + Sim Delay controls (compact bar) ---
        # We insert this bar at the top settings area, reusing existing layout if available.
        # Fallback to main_layout if structure changes in the .ui later.
        target_layout = getattr(self.ui, "top_settings_layout", None)
        if target_layout is None:
            target_layout = self.ui.main_layout

        self.runtime_options_group = QtWidgets.QGroupBox("Runtime options", self)
        options_layout = QtWidgets.QHBoxLayout(self.runtime_options_group)
        
        # Control checkbox (bitwise decode in logs)
        self.control_checkbox = QtWidgets.QCheckBox("Control: bitwise decode in logs", self.runtime_options_group)
        self.control_checkbox.setChecked(True)
        self.control_checkbox.setToolTip("When enabled, responses are explained bit-by-bit in the logs panel.")
        self.control_checkbox.stateChanged.connect(self.changeControlCheckBox)
        options_layout.addWidget(self.control_checkbox)

        # Frame format radios
        self.frame_short_radio = QtWidgets.QRadioButton("Short frame", self.runtime_options_group)
        self.frame_long_radio  = QtWidgets.QRadioButton("Long frame", self.runtime_options_group)
        self.frame_long_radio.setChecked(True)  # default
        frame_group_box = QtWidgets.QGroupBox("Frame format", self.runtime_options_group)
        frame_box_layout = QtWidgets.QHBoxLayout(frame_group_box)
        frame_box_layout.addWidget(self.frame_short_radio)
        frame_box_layout.addWidget(self.frame_long_radio)
        options_layout.addWidget(frame_group_box)

        # Simulation delay
        self.delay_label = QtWidgets.QLabel("Sim delay (ms):", self.runtime_options_group)
        self.delay_spinbox = QtWidgets.QSpinBox(self.runtime_options_group)
        self.delay_spinbox.setRange(0, 5000)
        self.delay_spinbox.setSingleStep(50)
        self.delay_spinbox.setValue(200)
        options_layout.addWidget(self.delay_label)
        options_layout.addWidget(self.delay_spinbox)

        # Stretch to keep UI neat
        options_layout.addStretch(1)

        # Insert the group near the top
        target_layout.insertWidget(0, self.runtime_options_group)


        # Save file buttons
        self.ui.send_data_save_button.clicked.connect(lambda: self.onSaveLog(self.ui.send_data_text_edit, "send_data"))
        self.ui.raw_data_save_button.clicked.connect(lambda: self.onSaveLog(self.ui.raw_data_text_edit, "raw_data"))
        self.ui.decrypted_data_save_button.clicked.connect(lambda: self.onSaveLog(self.ui.decrypted_data_text_edit, "decrypted_data"))
        # --- in MenuBar
        self.ui.actionSave_Send_Data_2.triggered.connect(lambda: self.onSaveLog(self.ui.send_data_text_edit, "send_data"))
        self.ui.actionSave_Raw_Data_2.triggered.connect(lambda: self.onSaveLog(self.ui.raw_data_text_edit, "raw_data"))
        self.ui.actionSave_Decrypted_Data_2.triggered.connect(lambda: self.onSaveLog(self.ui.decrypted_data_text_edit, "decrypted_data"))

        # Load file for Send Data textEdit
        self.ui.send_data_load_button.clicked.connect(lambda: self.onLoadSendData(self.ui.send_data_text_edit))
        # --- in MenuBar
        self.ui.actionLoad_Send_Data_2.triggered.connect(lambda: self.onLoadSendData(self.ui.send_data_text_edit))

        # Clear fields buttons hendlers
        self.ui.send_data_clear_button.clicked.connect(lambda: self.onClear([self.ui.send_data_text_edit]))
        self.ui.raw_data_clear_button.clicked.connect(lambda: self.onClear([self.ui.raw_data_text_edit]))
        self.ui.decrypted_data_clear_button.clicked.connect(lambda: self.onClear([self.ui.decrypted_data_text_edit]))
        self.ui.clear_device_button.clicked.connect(lambda: self.onClear([self.ui.device_address_hex, self.ui.device_id_dec]))

        # --- Optional: small polish for Logs tab ---
        # If the "Data Logs and Manual Packets" tab exists, add a filter combobox (non-breaking).
        # We will not rely on specific object names; we check dynamically.
        try:
            # Find tab index by title
            tabw = self.ui.tab_widget
            logs_index = None
            for i in range(tabw.count()):
                if "Logs" in tabw.tabText(i):
                    logs_index = i
                    break
            if logs_index is not None:
                logs_tab = tabw.widget(logs_index)
                top_bar = QtWidgets.QHBoxLayout()
                self.log_filter_combo = QtWidgets.QComboBox(logs_tab)
                self.log_filter_combo.addItems(["All", "Only Requests", "Only Responses"])
                self.log_filter_combo.setToolTip("Filter visible log entries")
                top_bar.addWidget(QtWidgets.QLabel("Log filter:", logs_tab))
                top_bar.addWidget(self.log_filter_combo)
                top_bar.addStretch(1)

                # Prepend to the logs tab main layout
                if isinstance(logs_tab.layout(), QtWidgets.QVBoxLayout):
                    logs_tab.layout().insertLayout(0, top_bar)
                else:
                    # Create a container if no layout found (future-proof)
                    v = QtWidgets.QVBoxLayout(logs_tab)
                    logs_tab.setLayout(v)
                    v.addLayout(top_bar)
        except Exception:
            # Silent: UI structure may differ; we don't break the app
            pass
    
    """
    Apply random [a,b] to Number of Preambles
    """
    def randomizeNumberOfPreambles(self, a = 3, b = 16):
        self.ui.num_preambles_edit.setText(str(random.randint(a, b)))
    
    """
    Control: Bitwise decode in logs checkbox change state action
    Action: clears all auto-commands QLineEdits
    """
    def changeControlCheckBox(self, state):

        # block inputs in commands 0, 1, 2, 3, 7, 8, 12, 13, 14, 16, 20, 38, 48,
        elements = (
            self.ui.command_0_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command_1_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command_2_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command3_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command_7_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command_8_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command_12_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command_13_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command_14_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command_16_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command_20_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command_38_group.findChildren(QtWidgets.QLineEdit) +
            self.ui.command_48_group.findChildren(QtWidgets.QLineEdit) 
        )

        # clear input fields if control_flag is unchecked
        if state != 2:  # state = { (0,1,2) ==> (unchecked, semi-checked, checked)  }
            for element in elements:
                # clears input`s text
                element.setText("")
    
    """
    Used for --LOAD-- text-file data to QWinget.text
    """
    def onLoadSendData(self, widget):
        options = QFileDialog.Options()
        file_name, selected_filter = QFileDialog.getOpenFileName(
            self,
            "Open Log File",
            "./logs/",
            "Text Files (*.txt);;Log Files (*.log);;All Files (*)",
            options=options
        )
        if file_name:
            try:
                with open(file_name, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Вставляем текст в переданный виджет
                if hasattr(widget, 'setPlainText'):
                    # для QTextEdit
                    widget.setPlainText(content)
                elif hasattr(widget, 'setText'):
                    # для QLineEdit
                    widget.setText(content)
                else:
                    print(f"Widget {widget} doesn't support text setting.")
            except Exception as e:
                print(f"Error loading file: {e}")

    """
    Used for --SAVE-- QWinget.text to file 
    """
    def onSaveLog(self, widget, filename):
        options = QFileDialog.Options()
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Log File",
            f"./logs/{filename}.txt",
            "Text Files (*.txt);;Log Files (*.log);;All Files (*)",
            options=options
        )

        if hasattr(widget, 'toPlainText'): # для QTextEdit
            log_content = widget.toPlainText()
        elif hasattr(widget, 'text'): # для QLineEdit
            log_content = widget.text()
        else:
            log_content = ""

        if file_name:
            try:
                with open(file_name, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                print(f"Log saved to {file_name}")
            except Exception as e:
                print(f"Error saving log: {e}")

    """
    Used to --CLEAR-- QWinget.text. Gets QWinget[]
    """
    def onClear(self, wingets):
        for element in wingets:
            if hasattr(element, "setText"):
                element.setText("")


def main():
    import sys
    app = QtWidgets.QApplication(sys.argv)
    win = HARTWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
