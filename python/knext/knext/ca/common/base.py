import asyncio
import os
from string import Template
from knext.ca.common.utils import logger


class Question(object):
    """
    This class models a question that may have dependencies on other questions
    and can also have sub-questions. It helps in structuring a complex problem
    into manageable parts, ensuring that each part can be addressed in a logical
    sequence.

    There are two possible relationships between questions:
    1. The content of one question depends on the answer to another question.
    2. One question can be broken down into several sub-questions.
    """

    def __init__(self, question, dependencies=[], children=[], parent=None, context=None):
        """
        Initialize a Question object.

        :param question: The content of the question.
        :param dependencies: A list of Question objects that this question depends on.
        :param children: A list of sub-questions (Question objects) for this question.
        :param parent: The parent question (if any).
        :param context: Additional context or information related to the question.
        """
        self.question = question
        self.dependencies = dependencies
        self.children = children
        self.parent = parent
        self.answer = None
        self.context = context

    def is_solved(self):
        return self.answer is not None

    def get_current_depth(self):
        """
        Calculate the depth of the current question in the hierarchy.

        :return: The depth of the question.
        """
        now_depth = 1
        now = self
        while now.parent:
            now = now.parent
            now_depth += 1
        return now_depth

    def __str__(self):
        """
        Return a string representation of the question, including dependencies, children, parent, and context.

        :return: A string representation of the question.
        """
        repr_str = f'''question: {self.question}\n'''
        # dependies
        repr_str += 'deps:\n'
        for ind, dep in enumerate(self.dependencies):
            repr_str += f'  dep_question {ind}: {dep.question}\n'

        # chilren
        repr_str += 'children:\n'
        for ind, child in enumerate(self.children):
            repr_str += f'  childe_question {ind}: {child.question}\n'

        # parent
        if self.parent:
            repr_str += f'parent:\n  {self.parent.question}\n'

        # context:
        if self.context:
            repr_str += f'context:{self.context}\n'
        return repr_str


class KagBaseModule(object):
    """
    KagBaseModule is an abstract base class designed to interact with language model (LLM) modules.
    This class handles the processing flow from the input question to the output generated by the LLM.
    It supports intermediate processing tools and additional information fetching tools.
    A significant feature of this class is the management of prompt templates used to communicate with the LLM.

    The class allows for default or custom prompt templates to be loaded, processed, and saved.
    If a computational context is indicated, it initializes and manages the state dictionary containing the prompt template.
    """

    def __init__(
            self,
            llm_module,
            use_default_prompt_template=True,
            is_prompt_template_cn=True,
            prompt_template_dir=None,
            is_computational=True,
    ):
        """
        Initializes the KagBaseModule.

        Parameters:
        llm_module: The language model module used for generating responses.
        use_default_prompt_template (bool): Flag to use the default prompt template.
        prompt_template_dir (str): Directory to load the prompt template from, if not using the default.
        is_computational (bool): Indicates if the module operates in a computational context, impacting prompt template usage.

        If the module is computational, it initializes the state dictionary with the prompt template.
        """
        self.llm_module = llm_module
        self.is_computational = is_computational
        self.intermediate_process_tools = []
        self.extra_info_fetch_tools = []

        if is_computational:
            self.use_default_prompt_template = use_default_prompt_template
            self.is_prompt_template_cn = is_prompt_template_cn
            self.prompt_template_dir = prompt_template_dir
            self.state_dict = self.init_state_dict()

    def connect_intermediate_process_tools(self, intermediate_process_tools):
        self.intermediate_process_tools = intermediate_process_tools

    def connect_extra_info_fetch_tools(self, extra_info_fetch_tools):
        self.extra_info_fetch_tools = extra_info_fetch_tools

    def process_intermediate_info(self, info_dict):
        if not isinstance(info_dict, StopAsyncIteration):
            for info_tool in self.intermediate_process_tools:
                info_tool.process(info_dict)

    def get_module_name(self):
        raise NotImplementedError

    def get_template_var_names(self):
        raise NotImplementedError

    def forward(self, question: Question):
        """
        Processes the input question through the language model module.

        Parameters:
        question (Question): The input question object containing the query.

        Returns:
        The post-processed output generated by the LLM.
        """
        prompt = self.preprocess(question)
        llm_output = self.llm_module.generate(prompt)
        post_processed_output = self.postprocess(question, llm_output)
        return post_processed_output

    async def async_forward(self, question: Question):
        return self.forward(question)

    def preprocess(self, question: Question):
        return question.question

    def postprocess(self, question: Question, llm_output):
        return llm_output

    def get_ca_default_prompt_template_dir(self):
        directory = os.path.dirname(os.path.abspath(__file__))
        directory = os.path.join(directory, '..', 'logic/modules')
        if self.is_prompt_template_cn:
            return os.path.join(directory, 'default_prompt_template')
        else:
            return os.path.join(directory, 'default_prompt_template_en')

    def load_prompt_template(self, prompt_dir):
        prompt_file_path = os.path.join(
            prompt_dir,
            f'{self.get_module_name()}.txt'
        )
        logger.info(f"##### {self.get_module_name()} prompt_file_path: {prompt_file_path} {os.path.exists(prompt_file_path)}")
        if os.path.exists(prompt_file_path):
            with open(prompt_file_path, 'r') as f:
                template_string = f.read()
            template_string = self.process_template_string_to_avoid_doller_problem(template_string)
        else:
            template_string = '''default prompt. edit it anyway'''
        return Template(template_string)

    def process_template_string_to_avoid_doller_problem(self, template_string):
        new_template_str = template_string.replace('$', '$$')
        for var in self.get_template_var_names():
            new_template_str = new_template_str.replace(f'$${var}', f'${var}')
        return new_template_str

    def save_prompt_template(self, prompt_dir, prompt_template):
        prompt_file_path = os.path.join(
            prompt_dir, f'{self.get_module_name()}.txt')
        with open(prompt_file_path, 'w') as f:
            f.write(prompt_template)

    def create_default_state_dict(self):
        default_prompt_template = self.load_prompt_template(
            self.get_ca_default_prompt_template_dir())
        state_dict = {
            'prompt_template': default_prompt_template,
        }
        return state_dict

    def save_state_dict(self, save_dir, state_dict):
        prompt_dir = os.path.join(save_dir, 'prompt_template')
        os.makedirs(prompt_dir, exist_ok=True)
        self.save_prompt_template(prompt_dir, state_dict['prompt_template'].template)

    def load_state_dict(self, save_dir):
        prompt_dir = os.path.join(save_dir, 'prompt_template')
        prompt_template = self.load_prompt_template(prompt_dir)
        state_dict = {
            'prompt_template': prompt_template,
        }
        return state_dict

    def does_state_dict_exists(self, save_dir):
        prompt_file_path = os.path.join(
            save_dir, 'prompt_template', f'{self.get_module_name()}.txt')
        return os.path.exists(prompt_file_path)

    def init_state_dict(self):
        """
        Initializes the state dictionary by loading or creating the prompt template.

        Returns:
        state_dict (dict): The state dictionary containing the prompt template.
        """
        if self.use_default_prompt_template:
            return self.create_default_state_dict()
        else:
            if self.prompt_template_dir:
                working_dir = self.prompt_template_dir
            else:
                working_dir = os.getcwd()
            if self.does_state_dict_exists(working_dir):
                state_dict = self.load_state_dict(working_dir)
            else:
                state_dict = self.create_default_state_dict()
                self.save_state_dict(working_dir, state_dict)
            return state_dict


class Agent(object):
    def __init__(self, extra_info_fetch_tools, intermediate_process_tools, **kwargs):
        self.queue = None
        self.ready_question_count = None
        self.solved_question_set = None
        self.ready_question_set = None
        self.remaining_question_set = None
        self.extra_info_fetch_tools = extra_info_fetch_tools
        self.intermediate_process_tools = intermediate_process_tools
        self.intermediate_process_tasks = []
        self.extra_output_dict = {}
        for extra_tool in self.extra_info_fetch_tools:
            extra_tool.connect_extra_output_dict(self.extra_output_dict)

    def solve_problem(self, question: Question, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.reset_context()
        result = loop.run_until_complete(self.solve_problem_impl(question, **kwargs))
        return result

    async def solve_problem_impl(self, question: Question, **kwargs):
        raise NotImplementedError

    def reset_context(self):
        self.remaining_question_set = set()
        self.ready_question_set = set()
        self.solved_question_set = set()
        self.ready_question_count = 0
        self.queue = asyncio.Queue()
        self.intermediate_process_tasks = []
        self.extra_output_dict = {}

    def process_intermediate_info(self, info_dict):
        if not isinstance(info_dict, StopAsyncIteration):
            for info_tool in self.intermediate_process_tools:
                info_tool.process(info_dict)

    async def is_question_deps_ready(self, question: Question):
        while True:
            all_solved = True
            for dep in question.dependencies:
                if not dep.is_solved():
                    all_solved = False
            if all_solved:
                break
            await asyncio.sleep(0.5)
        return

    async def is_question_children_ready(self, question: Question):
        while True:
            all_solved = True
            for child in question.children:
                if not child.is_solved():
                    all_solved = False
            if all_solved:
                break
            await asyncio.sleep(0.5)
        return