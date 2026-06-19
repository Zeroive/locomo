import json
import os, re
import base64

header = """
<!DOCTYPE html>
<html>
<head>
    <title>Chat Example</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f0f0f0;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
        }
        .chat {
            display: flex;
            flex-direction: column;
        }
        .message {
            margin-bottom: 10px;
            padding: 10px;
            border-radius: 10px;
            font-size: 16px;
            max-width: 80%;
            word-wrap: break-word;
        }
        .sender1 {
            background-color: #e2f0cb;
            align-self: flex-start;
        }
        .sender2 {
            background-color: #b2ebf2;
            align-self: flex-end;
        }
        .date {
            background-color: #ffb6c1;
            align-self: center;
        }
        .message img {
            max-width: 100%;
            height: auto;
            margin-top: 10px;
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="chat">
    """

speaker_1_div = """
        <div class="message sender1">
            <p>%s</p>
        </div>
"""
    
speaker_2_div = """
        <div class="message sender2">
            <p>%s</p>
        </div>
"""

date_time_div = """
            <div class="message date">
                <p> &nbsp; &nbsp;%s&nbsp; &nbsp;</p>
            </div>
"""

def get_speaker_info(speaker, use_events=False):
    """
    获取说话人信息的HTML格式字符串。
    
    提取说话人的基本信息和人格描述，格式化为HTML片段。
    
    Args:
        speaker: 说话人对象，包含name和persona_summary等字段
        use_events: 是否包含事件信息（当前未使用）
        
    Returns:
        str: HTML格式的说话人信息字符串
    """

    output = ""
    output += "<b>Name</b>: " + speaker["name"] + '<br>'
    # output += "<b>Age</b>: " + str(speaker["age"]) + '<br>'
    # output += "<b>Gender</b>: " + speaker["gender"] + '<br>'
    if 'persona_summary' in speaker:
        output += "<b>Persona</b>: " + speaker["persona_summary"] + '<br>'

    # for k, v in speaker['persona'].items():
    #     if type(v) == list:
    #         value = ', '.join(v)
    #     else:
    #         value = v
    #     output += '<b>' + k + '</b>' + ': ' + value + '<br>'

    # if use_events:
    #     output += '<b>' + 'Events' + '</b>' + '<br>'
    #     for e in speaker['events']:
    #         output += '<b>' + e['date'] + '</b>' + ': ' + e['event'] + '<br>'

    return output

def get_session_events(events):
    """
    获取会话事件的HTML格式字符串。
    
    将事件列表格式化为带日期标签的HTML列表。
    
    Args:
        events: 事件列表，每个事件包含date和sub-event字段
        
    Returns:
        str: HTML格式的事件描述字符串
    """

    output = '<b>' + 'Events' + '</b>' + '<br>'
    for e in events:
        output += '<b>' + e['date'] + '</b>' + ': ' + e['sub-event'] + '<br>'
    return output


def convert_to_chat_html(speaker_1, speaker_2, outfile="", use_events=False):
    """
    将对话数据转换为可浏览的HTML聊天页面。
    
    生成一个完整的HTML文件，包含两个说话人的信息、所有会话记录
    和对话内容。使用不同的背景色区分两个说话人的消息。
    
    Args:
        speaker_1: 第一个说话人对象，包含会话数据
        speaker_2: 第二个说话人对象，包含会话数据
        outfile: 输出HTML文件路径，默认为空字符串
        use_events: 是否在输出中包含事件信息
        
    Returns:
        None（生成的文件写入outfile指定路径）
    """

    body = header
    # add persona
    
    body += speaker_1_div % get_speaker_info(speaker_1, use_events=use_events)
    body += speaker_2_div % get_speaker_info(speaker_2, use_events=use_events)

    # add session
    for num in range(1, 50):
        
        if 'session_%s' % num not in speaker_1:
            break
        
        if 'session_%s_date_time' % num in speaker_1:
            date_time_string = speaker_1['session_%s_date_time' % num]
        elif 'session_%s_date' % num in speaker_1:
            date_time_string = speaker_1['session_%s_date' % num]
        else:
            raise ValueError
        
        body += date_time_div % ("Session %s [ %s ]" % (num, date_time_string))

        if 'events_session_%s' % num in speaker_1 and 'events_session_%s' % num in speaker_2:
            speaker_1_events = speaker_1['events_session_%s' % num]
            speaker_2_events = speaker_2['events_session_%s' % num]

            body += speaker_1_div % get_session_events(speaker_1_events)
            body += speaker_2_div % get_session_events(speaker_2_events)

        for dialog in speaker_1['session_%s' % num]:
            text = dialog["clean_text"]
            selected_div = speaker_1_div if dialog["speaker"] == speaker_1["name"] else speaker_2_div
            body += selected_div % text
    body += """
        </div>
    </div>
</body>
</html>
"""
    with open(outfile, 'w') as fhtml:
        fhtml.write(body)

