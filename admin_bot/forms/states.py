from aiogram.fsm.state import State, StatesGroup


class AddChannel(StatesGroup):
    awaiting_target = State()
    confirming = State()


class ManageAdmins(StatesGroup):
    awaiting_user_id = State()
