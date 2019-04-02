# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pendulum
from PyQt5.QtCore import Qt, pyqtSignal, QCoreApplication
from PyQt5.QtWidgets import QWidget, QMenu
from PyQt5.QtGui import QPixmap

from parsec.crypto import build_revoked_device_certificate
from parsec.core.backend_connection import BackendNotAvailable, BackendCmdsBadResponse

from parsec.core.gui.register_user_dialog import RegisterUserDialog
from parsec.core.gui.custom_widgets import TaskbarButton, show_error, ask_question, show_info
from parsec.core.gui.core_widget import CoreWidget
from parsec.core.gui.ui.user_button import Ui_UserButton
from parsec.core.gui.ui.users_widget import Ui_UsersWidget


class UserButton(QWidget, Ui_UserButton):
    revoke_clicked = pyqtSignal(QWidget)

    def __init__(self, user_name, is_current_user, certified_on, is_revoked, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setupUi(self)
        if is_current_user:
            self.label.setPixmap(QPixmap(":/icons/images/icons/owner2.png"))
        else:
            self.label.setPixmap(QPixmap(":/icons/images/icons/user2.png"))
        self.name = user_name
        self.label.is_revoked = is_revoked
        self.certified_on = certified_on
        self.is_current_user = is_current_user
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value
        if len(value) > 16:
            value = value[:16] + "-\n" + value[16:]
        self.label_user.setText(value)

    @property
    def is_revoked(self):
        return self.label.is_revoked

    @is_revoked.setter
    def is_revoked(self, value):
        self.label.is_revoked = value
        self.label.repaint()

    def show_context_menu(self, pos):
        global_pos = self.mapToGlobal(pos)
        menu = QMenu(self)
        action = menu.addAction(QCoreApplication.translate("UserButton", "Show info"))
        action.triggered.connect(self.show_info)
        if not self.label.is_revoked and not self.is_current_user:
            action = menu.addAction(QCoreApplication.translate("UserButton", "Revoke"))
            action.triggered.connect(self.revoke)
        menu.exec_(global_pos)

    def show_info(self):
        text = "{}\n\n".format(self.name)
        text += QCoreApplication.translate("UserButton", "Created on {}").format(
            self.certified_on.format("%x %X")
        )
        if self.label.is_revoked:
            text += QCoreApplication.translate("UserButton", "\n\nThis user has been revoked.")
        show_info(self, text)

    def revoke(self):
        self.revoke_clicked.emit(self)


class UsersWidget(CoreWidget, Ui_UsersWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setupUi(self)
        self.users = []
        self.taskbar_buttons = []
        button_add_user = TaskbarButton(icon_path=":/icons/images/icons/plus_off.png")
        button_add_user.clicked.connect(self.register_user)
        self.taskbar_buttons.append(button_add_user)
        self.line_edit_search.textChanged.connect(self.filter_users)

    def get_taskbar_buttons(self):
        return self.taskbar_buttons

    def filter_users(self, pattern):
        pattern = pattern.lower()
        for i in range(self.layout_users.count()):
            item = self.layout_users.itemAt(i)
            if item:
                w = item.widget()
                if pattern and pattern not in w.name.lower():
                    w.hide()
                else:
                    w.show()

    def register_user(self):
        d = RegisterUserDialog(parent=self, portal=self.portal, core=self.core)
        d.exec_()
        self.reset()

    def add_user(self, user_name, is_current_user, certified_on, is_revoked):
        if user_name in self.users:
            return
        button = UserButton(user_name, is_current_user, certified_on, is_revoked)
        self.layout_users.addWidget(button, int(len(self.users) / 4), int(len(self.users) % 4))
        button.revoke_clicked.connect(self.revoke_user)
        self.users.append(user_name)

    def revoke_user(self, user_button):
        user_name = user_button.name
        result = ask_question(
            self,
            QCoreApplication.translate("UsersWidget", "Confirmation"),
            QCoreApplication.translate(
                "UsersWidget", 'Are you sure you want to revoke user "{}" ?'
            ).format(user_name),
        )
        if not result:
            return

        try:
            user_info, trustchain = self.portal.run(
                self.core.fs.backend_cmds.user_get, user_button.name
            )
            for device in user_info.devices.values():
                revoked_device_certificate = build_revoked_device_certificate(
                    self.core.device.device_id,
                    self.core.device.signing_key,
                    device.device_id,
                    pendulum.now(),
                )
                self.portal.run(self.core.fs.backend_cmds.device_revoke, revoked_device_certificate)
            user_button.is_revoked = True
            show_info(
                self,
                QCoreApplication.translate("UsersWidget", 'User "{}" has been revoked.').format(
                    user_name
                ),
            )
        except BackendCmdsBadResponse as exc:
            if exc.status == "already_revoked":
                show_error(
                    self,
                    QCoreApplication.translate(
                        "UsersWidget", 'User "{}" has already been revoked.'
                    ).format(user_name),
                )
            elif exc.status == "not_found":
                show_error(
                    self,
                    QCoreApplication.translate("UsersWidget", 'User "{}" not found.').format(
                        user_name
                    ),
                )
            elif exc.status == "invalid_role" or exc.status == "invalid_certification":
                show_error(
                    self,
                    QCoreApplication.translate(
                        "UsersWidget", "You don't have the permission to revoke this user."
                    ),
                )
        except:
            show_error(self, QCoreApplication.translate("UsersWidget", "Can not revoke this user."))

    def reset(self):
        self.line_edit_search.setText("")
        self.users = []
        while self.layout_users.count() != 0:
            item = self.layout_users.takeAt(0)
            if item:
                w = item.widget()
                self.layout_users.removeWidget(w)
                w.setParent(None)
        if self.portal and self.core:
            try:
                user_id = self.core.device.user_id
                users = self.portal.run(self.core.fs.backend_cmds.user_find)
                for user in users:
                    user_info, user_devices = self.portal.run(
                        self.core.remote_devices_manager.get_user_and_devices, user
                    )
                    self.add_user(
                        str(user_info.user_id),
                        is_current_user=user_id == user,
                        certified_on=user_info.certified_on,
                        is_revoked=all([device.revoked_on for device in user_devices]),
                    )
            except BackendNotAvailable:
                pass
            except:
                pass
