from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    choosing_type = State()
    entering_subject = State()
    entering_topic = State()
    entering_description = State()
    waiting_photos = State()
    waiting_more_photos = State()
    waiting_pdf = State()
    entering_measurements = State()
    entering_requirements = State()
    entering_style = State()
    entering_custom_style = State()
    confirming_order = State()
    waiting_payment = State()


class EditStates(StatesGroup):
    choosing_edit_type = State()
    entering_free_edit = State()
    confirming_paid_edit = State()
    entering_slide_number = State()
    entering_section_content = State()


class AdminStates(StatesGroup):
    in_admin = State()
    entering_vip_id = State()
    removing_vip_id = State()
    confirming_vip_remove = State()
    searching_user = State()
    refunding = State()
    confirming_refund = State()
    broadcasting = State()
    broadcast_preview = State()
    editing_price = State()
    rejecting_payment_custom = State()


class TopUpStates(StatesGroup):
    waiting_amount = State()


class BalanceStates(StatesGroup):
    choosing_method = State()
    entering_custom_amount = State()


class ReferralStates(StatesGroup):
    entering_code = State()


class SubscriptionStates(StatesGroup):
    confirming_purchase = State()
