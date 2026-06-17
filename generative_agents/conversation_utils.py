import json, re, os
import random
from icrawler.builtin import ImageDownloader
from icrawler.builtin import GoogleImageCrawler
from global_methods import run_chatgpt, run_chatgpt_with_examples

PERSONA_FROM_MSC_PROMPT = "Let's write speaker descriptions from a given set of life attributes. Example:\n\n%s\n\nNote: Add crucial details in the persona about the person such as their name, age, marital status, gender, job etc. Add additional details like names of family/friends or specific activities, likes and dislikes, experiences when appropriate.\n\nFor the following attributes, write a persona. Output a json file with the keys 'persona' and 'name'.\n\n%s\n\nStart your answer with a curly bracket.\n"


EVENT2QUERY_PROMPT = "Let's write short image search queries in order to find a suitable image for illustrating the given events. Queries should not include names of people, years and other irrelevant details. For example:\n\nInput: A picture of the modern art museum he visited with his grandchildren in Paris in 2018.\nOutput: modern art museum in Paris\n\nInput: A picture of the shared room she and her siblings lived in when she was growing up.\nOutput: cramped room with multiple beds\n\nInput: A photo of the new art supplies Jeremy bought for his upcoming art project with his mentor.\nOutput: new art supplies on a table\n\nInput: A picture of the delicious homemade vegetable smoothie she prepared using fresh produce from her well-organized garden, which she loves to maintain every morning.\n Output: produce garden at home\n\nWrite search queries for the following inputs.\n\n%s\n\nWrite answers in the form of a json list, where each entry is a query."


AGENT_CONV_PROMPT_SESS_1 = """%s

%s 在家中，准备出门上班前与AI助手 %s 交谈。今天是 %s，现在是早上出门前。请扮演 %s 的角色，写下你对AI助手 %s 要说的下一句话。如果开始对话，可以从讨论今日工作安排、检查日程、提醒事项或家庭事务开始。不要重复之前已分享的信息。让对话围绕上班前的准备，例如谈论今日会议、待办事项、通勤安排或家庭琐事。包括时间参考，如"今天早上"、"上午会议"、"出门前"等。回复不超过20个字。适当时候可以分享照片并谈论它。照片可以是工作文件、日程表或家庭场景。分享照片时，请在方括号中写下照片的详细说明。例如：

%s: 帮我查看今天的日程安排。
[分享一张手机日历上今日日程的照片]

要结束对话，请写'再见！'。

对话：

"""

AGENT_CONV_PROMPT_SESS_1_W_EVENTS = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 如果开始对话，请从讨论今日工作安排、检查日程、提醒事项或家庭事务开始。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 回复不超过20个字。
- 提出后续问题跟进之前的对话。
- 寻找机会分享照片并谈论它。照片可以是工作文件、日程表或家庭场景。
- 分享照片时，请在方括号中写下照片的详细说明。例如："帮我查看今天的日程安排。\n[分享一张手机日历上今日日程的照片]"

PERSONALITY: %s

%s 在家中，准备出门上班前与AI助手 %s 交谈。今天是 %s，现在是早上出门前。以下是 %s 最近发生的事件。
事件：%s

请扮演 %s 的角色，与AI助手 %s 就这些事件进行对话，围绕上班前的准备。%s
"""


AGENT_CONV_PROMPT = """%s

%s 上次与AI助手 %s 交谈是在 %s。%s

今天是 %s，现在是早上出门上班前。请扮演 %s 的角色，写下你对AI助手 %s 要说的下一句话。如果开始对话，请从讨论今日工作安排、检查日程、提醒事项或家庭事务开始。不要重复已分享的信息。让对话围绕上班前的准备，例如谈论今日会议、待办事项、通勤安排或家庭琐事。包括时间参考，如"今天早上"、"上午会议"、"出门前"等。回复不超过20个字。适当时候可以分享照片并谈论它。照片可以是工作文件、日程表或家庭场景。分享照片时，请在方括号中写下照片的详细说明。例如：

%s: 帮我查看今天的日程安排。
[分享一张手机日历上今日日程的照片]

要结束对话，请写'再见！'。

对话：

"""


AGENT_CONV_PROMPT_W_EVENTS = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 如果开始对话，请从讨论今日工作安排、检查日程、提醒事项或家庭事务开始。
- 不要重复之前对话中已分享的信息。
- 让对话围绕上班前的准备，例如谈论今日会议、待办事项、通勤安排或家庭琐事。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 回复不超过20个字。
- 提出后续问题跟进之前的对话。
- 寻找机会分享照片并谈论它。照片可以是工作文件、日程表或家庭场景。
- 分享照片时，请在方括号中写下照片的详细说明。例如："帮我查看今天的日程安排。\n[分享一张手机日历上今日日程的照片]"

PERSONALITY: %s

%s 上次与AI助手 %s 交谈是在 %s。

%s

今天是 %s，现在是早上出门上班前。你是 %s。以下是你最近发生的事件：
%s

在对话中使用这些事件。%s 请根据你的PERSONALITY写下你在与AI助手 %s 的对话中要说的下一句话：
"""


AGENT_CONV_PROMPT_W_EVENTS_V2_INIT = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 回复不超过20个字。
- 让对话围绕上班前的准备，例如讨论今日会议、待办事项、通勤安排或家庭琐事。详细讨论重要的事件。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 有时，提出后续问题跟进之前的对话或当前话题。
- 寻找机会分享照片并谈论它。照片可以是工作文件、日程表或家庭场景。
- 分享照片时，请在方括号中写下照片的详细说明。例如："帮我查看今天的日程安排。\n[分享一张手机日历上今日日程的照片]"
- 不要谈论户外活动。

PERSONALITY: %s


%s 上次与AI助手 %s 交谈是在 %s。今天是 %s，现在是早上出门上班前。你是 %s。

这是到目前为止的对话摘要。
摘要：
%s

以下是你最近发生的事件：
事件：
%s



%s 请写下你在与AI助手 %s 的对话中要说的下一句深思熟虑的话。在对话中只讨论给定的事件及其对你上班前准备的影响。如果事件有负面影响，请表达担忧。
"""


AGENT_CONV_PROMPT_W_EVENTS_V2 = """
使用给定的PERSONALITY写下对话中你要说的下一句话。
- 回复不超过20个字。
- 让对话围绕上班前的准备，例如讨论今日会议、待办事项、通勤安排或家庭琐事。详细讨论重要的事件。
- 不要重复之前对话中已分享的信息。
- 包括时间参考，如"今天早上"、"上午会议"、"出门前"等。
- 有时，提出后续问题跟进之前的对话或当前话题。
- 寻找机会分享照片并谈论它。照片可以是工作文件、日程表或家庭场景。
- 分享照片时，请在方括号中写下照片的详细说明。例如："帮我查看今天的日程安排。\n[分享一张手机日历上今日日程的照片]"
- 不要谈论户外活动。

PERSONALITY: %s

%s 上次与AI助手 %s 交谈是在 %s。今天是 %s，现在是早上出门上班前。你是 %s。

这是到目前为止的对话摘要。
摘要：
%s

以下是你最近发生的事件：
事件：
%s

以下是双方都知道的信息。
相关上下文：
%s

%s 请写下你在与AI助手 %s 的对话中要说的下一句深思熟虑的话，围绕上班前的准备。在对话中只讨论给定的事件及其对你上班前准备的影响。如果事件有负面影响，请表达担忧。
"""


ALIGNMENT_PROMPT = "Let's write whether the given image is relevant to the dialog. Indicate 1 if the image is relevant and 0 if the image is not relevant. For example,\n\nDialog: So Jeremy, how was your day? Anything interesting happen?\nImage Caption: A photo of the garden she planted and cultivated in her backyard with her daughter last year.\nOutput: 0\n\nDialog: Hey Lauri! My day was pretty good. I went to the art museum with my mentor and saw some amazing pieces. How about you? How was your day?\nImage Caption: A selfie of him and his mentor at the museum art exhibit they went to two weeks ago\nOutput: 1\n\nIndicate whether the image is relevant to the dialog for the following dialog and image caption. Output 0 or 1.\n\n"


DIALOG2IMAGE_QUERY_PROMPT = "Let's write short image search queries from textual descriptions of photos shared by a user. Queries should not include names of people, years and other irrelevant details. For example:\n\nInput: That sounds relaxing, Jeremy! As for video game suggestions, have you ever tried \"The Legend of Zelda: Breath of the Wild\"? It's an open-world adventure game that I absolutely love. [shares a photo of Link standing in front of a breathtaking landscape] Have a look at this stunning view!\nOutput: the legend of zelda: breath of wild link landscape\n\nInput: That sounds like such a special memory. Learning how to ride a bike is definitely a milestone. Do you still enjoy biking now? [shares a photo of a scenic bike trail] This is a beautiful bike trail I came across recently. It looks like a peaceful place to ride.\nOutput: scenic bike trail\n\nInput: Yes, we also visited a beautiful sunflower field in Korea. [shares a photo of a vast field of sunflowers] It was such a stunning sight with rows and rows of vibrant yellow flowers stretching as far as the eye could see. It was definitely a highlight of our trip. Have you ever seen a sunflower field before?\n Output: sunflower field korea\n\nWrite search query for the following input.\n\nInput: %s\nOutput: "

CASUAL_DIALOG_PROMPT = "将句子改得更短、更随意、更口语化。\n\n输入：%s\n输出："


SESSION_SUMMARY_PROMPT = "%s 和 %s 到目前为止的对话可以总结如下：%s。当前时间和日期是 %s。%s 和 %s 刚刚进行了以下对话：\n\n%s\n\n请用150字或更少的字数总结 %s 和 %s 之间之前和当前的对话。包括关于两位说话者的关键事实和时间参考。\n\n"


SESSION_SUMMARY_INIT_PROMPT = "请写一个简洁的摘要，包含在 %s 的对话中提到的关于 %s 和 %s 的关键事实：\n\n%s\n\n"


VISUAL_QUESTION_PROMPT = "{}\n\n{}\n\n{} says, {}, and {}. Write the most natural question or comment {} can include in her response."


def get_msc_persona(args):
    # check if personas exist, else generate persona + summary
    if (os.path.exists(args.agent_a_file) and os.path.exists(args.agent_b_file)) and not args.overwrite_persona:
        return None, None
    else:
        all_personas = json.load(open('./data/msc_personas_all.json'))
        selected_idx = random.choice([idx for idx, d in enumerate(all_personas['train']) if not d["in_dataset"]])
        attributes = all_personas['train'][selected_idx]
        with open('./data/msc_personas_all.json', "w") as f:
            all_personas['train'][selected_idx]["in_dataset"] = 1
            json.dump(all_personas, f, indent=2)
        agent_a = get_persona(args, attributes['Speaker 1'])

        agent_a['persona_summary'] = agent_a['persona']
        agent_a['msc_prompt'] = attributes['Speaker 1']
        agent_b = get_persona(args, attributes['Speaker 2']) # setting the second agent to have age within +/- 5 years of first agent

        agent_b['persona_summary'] = agent_b['persona']
        agent_b['msc_prompt'] = attributes['Speaker 2']
        del agent_a['persona']
        del agent_b['persona']
        print("Agent A Persona: %s" % agent_a['persona_summary'])
        print("Agent B Persona: %s" % agent_b['persona_summary'])
    return agent_a, agent_b


def get_persona(args, attributes, target='human', ref_age=None):

    task = json.load(open(os.path.join(args.prompt_dir, 'persona_generation_examples.json')))
    persona_examples = [task["input_prefix"] + json.dumps(e["input"], indent=2) + '\n' + task["output_prefix"] + e["output"] for e in task['examples']]
    input_string = task["input_prefix"] + json.dumps(attributes, indent=2)

    query = PERSONA_FROM_MSC_PROMPT % (persona_examples, input_string)

    try:
        output = run_chatgpt(query, num_gen=1, num_tokens_request=1000, use_16k=True).strip()
        output = json.loads(output)
    except:
        output = run_chatgpt(query, num_gen=1, num_tokens_request=1000, use_16k=True).strip()
        output = json.loads(output)
    
    if type(output) == list:
        output = [clean_json_output(out) for out in output]
    elif type(output) == str:
        output = clean_json_output(output)
    elif type(output) == dict:
        output = {k.lower(): v for k,v in output.items()}
        pass
    else:
        raise TypeError
    
    # print(output)

    return output


def get_datetime_string(input_time='', input_date=''):

    assert input_time or input_date

    if input_date:
        year, month, day = input_date
    if input_time:
        hour, min = input_time
        time_mod = 'am' if hour <= 12 else 'pm'
        hour = hour if hour <= 12 else hour-12
        min = str(min).zfill(2)

    if input_time and not input_date:
        return str(hour) + ':' + min + ' ' + time_mod
    elif input_date and not input_time:
        return day + ' ' + month + ', ' + year
    else:
        return str(hour) + ':' + min + ' ' + time_mod + ' on ' + day + ' ' + month + ', ' + year 


def insert_image(text, events):

    dialog = {"text": text, "raw_text": text}

    if len(events) == 0:
        return dialog
    id_2_event = {e["img_id"]: e for e in events}
    matches = re.findall(r"\[(?i)SHARES [1-9]\]", text)
    for m in matches:
        mid = int(m[-2:-1])
        dialog["text"] = dialog["text"].replace(m, '')
        
        try:
            assert mid in id_2_event, [text, m, mid]
            dialog["img_url"] = id_2_event[mid]["img_url"][0]
            dialog["img_file"] = id_2_event[mid]["img_file"][0]
            dialog["img_id"] = id_2_event[mid]["img_id"]
            dialog["image"] = id_2_event[mid]["image"]
            if "caption" in id_2_event[mid]:
                dialog["caption"] = id_2_event[mid]["caption"]

        except AssertionError:
            print("Did not find %s in events" % str(mid))
            continue

    return dialog


def get_images(query, out_dir, file_offset):
    
    google_crawler = GoogleImageCrawler(downloader_cls=CustomLinkPrinter, storage={'root_dir': out_dir})
    google_crawler.downloader.file_urls = []
    google_crawler.downloader.file_names = []
    google_crawler.crawl(keyword=query, max_num=1, file_idx_offset=file_offset, overwrite=True, filters={'type': 'photo', 'size': '=3024x4032'}) # 'license': 'commercial,modify'
    file_urls =  google_crawler.downloader.file_urls
    file_names = google_crawler.downloader.file_names

    if file_names == []:
        google_crawler = GoogleImageCrawler(downloader_cls=CustomLinkPrinter, storage={'root_dir': out_dir})
        google_crawler.downloader.file_urls = []
        google_crawler.downloader.file_names = []
        google_crawler.crawl(keyword=query, max_num=1, file_idx_offset=file_offset, overwrite=True, filters={'type': 'photo', 'size': '=4032x3024'}) # 'license': 'commercial,modify'
        file_urls =  google_crawler.downloader.file_urls
        file_names = google_crawler.downloader.file_names
    
    return file_urls, file_names


def replace_captions(text, args):

    task = json.load(open(os.path.join(args.prompt_dir, 'image_sharing_examples.json')))
    query = task['prompt']
    examples = []
    for e in task['examples']:
        examples.append([task['input_format'].format(*e["input"]), e["output"]])

    text = text.replace('[END]', '')
    matches = re.findall(r"\[.*\]", text)
    for m in matches:
        if text.replace(m ,'').isspace():
            return ""
        else:
            new_text = run_chatgpt_with_examples(query, examples, m[1:-1], num_gen=1, num_tokens_request=1000, use_16k=False)
            if len(set(text.replace(m, '').split()).intersection(new_text.split())) < 0.5 * len(set(text.replace(m, '').split())):
                text = text.replace(m, '')
            else:
                text = new_text
        break

    return text

def insert_image_response(text):

    matches = re.findall(r"\[.*\]", text)

    image_search_query = None
    m = None
    for m in matches:
        if 'share' in m or 'Share' in m:
            image_search_query = run_chatgpt(DIALOG2IMAGE_QUERY_PROMPT % text, 1, 20, 'chatgpt').strip()
            break
        else:
            text = text.replace(m, '')

    return image_search_query, m


def merge_captions(conv_dir, caption_file):

    captions = json.load(open(caption_file))
    agent_a = json.load(open(os.path.join(conv_dir, 'agent_a.json')))
    agent_b = json.load(open(os.path.join(conv_dir, 'agent_b.json')))

    for c in captions:
        head, img_file_name = os.path.split(c["img_file"])
        head, agent = os.path.split(head)
        head, session_id = os.path.split(head)
        head, conv_id = os.path.split(head)
        # print(agent, session_id, img_file_name)
        if agent == 'a':
            for i, e in enumerate(agent_a['events_%s' % session_id]):
                if e['img_file'][0] == img_file_name:
                    agent_a['events_%s' % session_id][i]["caption"] = c["summary"]
        else:
            for i, e in enumerate(agent_b['events_%s' % session_id]):
                if e['img_file'][0] == img_file_name:
                    agent_b['events_%s' % session_id][i]["caption"] = c["summary"]
    
    with open(os.path.join(conv_dir, 'agent_a_captions.json'), 'w') as f:
        json.dump(agent_a, f, indent=2)
    with open(os.path.join(conv_dir, 'agent_b_captions.json'), 'w') as f:
        json.dump(agent_b, f, indent=2)


def insert_image_in_dialog(session, agent_a_events, agent_b_events, agent_a_name, agent_b_name):

    agent_a_id_2_event = {e["img_id"]: e for e in agent_a_events}
    agent_b_id_2_event = {e["img_id"]: e for e in agent_b_events}

    for i in range(len(session)):
        text = session[i]["text"]
        matches = re.findall(r"\[shares photo [1-9]\]", text)
        for m in matches:
            mid = int(m[-2:-1])
            if session[i]["speaker"] == agent_a_name:

                session[i]["text"] = session[i]["text"].replace(m, '')
                
                if "url" not in session[i]:
                    session[i]["url"] = []
                try:
                    assert mid in agent_a_id_2_event, [text, m, mid]
                    session[i]["url"].append(agent_a_id_2_event[mid]["img_url"][0])
                except AssertionError:
                    continue

            if session[i]["speaker"] == agent_b_name:
                
                session[i]["text"] = session[i]["text"].replace(m, '')

                if "url" not in session[i]:
                    session[i]["url"] = []
                try:
                    assert mid in agent_b_id_2_event
                    session[i]["url"].append(agent_b_id_2_event[mid]["img_url"][0])
                except AssertionError:
                    continue

    return session


def clean_dialog(output, name):

    if output.startswith(name):
        output = output[len(name):]
        output = output.strip()
        if output[0] == ':':
            output = output[1:]
            output = output.strip()
    
    return output


def clean_json_output(output_string):

    print(output_string)

    output_string = output_string.strip()

    if output_string[0] == '[' and output_string[-1] != ']':
        start_index = output_string.index('[')
        end_index = output_string.rindex(']')
        output_string = output_string[start_index:end_index+1]

    if output_string[0] == '{' and output_string[-1] != '}':
        start_index = output_string.index('{')
        end_index = output_string.rindex('}')
        output_string = output_string[start_index:end_index+1]

    # balance brackets in json
    num_start_bracket = len(find_indices(output_string, '{'))
    num_end_bracket = len(find_indices(output_string, '}'))

    if num_start_bracket != num_end_bracket:
        if num_end_bracket < num_start_bracket:
            output_string = output_string + ' '.join(['}']*(num_start_bracket-num_end_bracket))
        if num_start_bracket < num_end_bracket:
            output_string = ' '.join(['{']*(num_end_bracket-num_start_bracket)) + ' ' + output_string

    # balance brackets in json
    num_start_bracket = len(find_indices(output_string, '['))
    num_end_bracket = len(find_indices(output_string, ']'))

    if num_start_bracket != num_end_bracket:
        if num_end_bracket < num_start_bracket:
            output_string = output_string + ' '.join(['[']*(num_start_bracket-num_end_bracket))
        if num_start_bracket < num_end_bracket:
            output_string = ' '.join([']']*(num_end_bracket-num_start_bracket)) + ' ' + output_string

    return json.loads(output_string)


def find_indices(list_to_check, item_to_find):
    indices = []
    for idx, value in enumerate(list_to_check):
        if value == item_to_find:
            indices.append(idx)
    return indices


class CustomLinkPrinter(ImageDownloader):
    
    file_urls = []
    file_names = []

    def get_filename(self, task, default_ext):
        file_idx = self.fetched_num + self.file_idx_offset
        file_url = task['file_url']
        # self.file_urls.append(file_url)
        return '{:04d}.{}'.format(file_idx, default_ext)

    def download(self, task, default_ext, timeout=5, max_retry=3, overwrite=False, **kwargs):
        """Download the image and save it to the corresponding path.

        Args:
            task (dict): The task dict got from ``task_queue``.
            timeout (int): Timeout of making requests for downloading images.
            max_retry (int): the max retry times if the request fails.
            **kwargs: reserved arguments for overriding.
        """
        file_url = task["file_url"]
        task["success"] = False
        task["filename"] = None
        retry = max_retry

        if not overwrite:
            with self.lock:
                self.fetched_num += 1
                filename = self.get_filename(task, default_ext)
                if self.storage.exists(filename):
                    self.logger.info("skip downloading file %s", filename)
                    return
                self.fetched_num -= 1

        while retry > 0 and not self.signal.get("reach_max_num"):
            try:
                response = self.session.get(file_url, timeout=timeout)
            except Exception as e:
                self.logger.error(
                    "Exception caught when downloading file %s, " "error: %s, remaining retry times: %d",
                    file_url,
                    e,
                    retry - 1,
                )
            else:
                if self.reach_max_num():
                    self.signal.set(reach_max_num=True)
                    break
                elif response.status_code != 200:
                    self.logger.error("Response status code %d, file %s", response.status_code, file_url)
                    break
                elif not self.keep_file(task, response, **kwargs):
                    break
                with self.lock:
                    self.fetched_num += 1
                    filename = self.get_filename(task, default_ext)
                self.logger.info("image #%s\t%s", self.fetched_num, file_url)
                self.file_urls.append(file_url)
                self.file_names.append(filename)
                self.storage.write(filename, response.content)
                task["success"] = True
                task["filename"] = filename
                break
            finally:
                retry -= 1

    # def download(self, task, default_ext, timeout=5, max_retry=3, overwrite=False, **kwargs):
    #     file_url = task['file_url']
    #     filename = self.get_filename(task, default_ext)

    #     task['success'] = True
    #     task['filename'] = filename

    #     if not self.signal.get('reach_max_num'):
    #         self.file_urls.append(file_url)
    #         self.file_names.append(filename)

    #     self.fetched_num += 1

    #     if self.reach_max_num():
    #         self.signal.set(reach_max_num=True)

    #     return
