import sys
from PyQt5 import QtWidgets
from gui.Window import HARTWindow
from controllers.hart_bus_controller import HARTBusController

def main():
    app = QtWidgets.QApplication(sys.argv)
    main_window = HARTWindow()
    main_window.setWindowTitle("HART Protocol Simulator")

    # Підключення контролера вкладки HART Bus Devices
    bus_controller = HARTBusController(main_window)  # noqa: F841
    main_window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
