import time

from plugins.repeater.model import Chat, ChatData


def test_chat():
    # Chat.clearup_context()
    # # while True:
    test_data: ChatData = ChatData(
        group_id=1234567,
        user_id=1111111,
        raw_message='完了又有新bug',
        plain_text='完了又有新bug',
        time=time.time(),
        bot_id=0,
    )

    test_chat = Chat(test_data)

    print(test_chat.answer())
    test_chat.learn()

    test_answer_data: ChatData = ChatData(
        group_id=1234567,
        user_id=1111111,
        raw_message='完了又有新bug',
        plain_text='完了又有新bug',
        time=time.time(),
        bot_id=0,
    )

    test_answer: Chat = Chat(test_answer_data)
    print(test_chat.answer())
    test_answer.learn()

    # time.sleep(5)
    # print(Chat.speak())
