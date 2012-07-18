import sublime
import sublime_plugin

import os
# todo(guillermooo): maybe allow other test frameworks?
import unittest
import StringIO
import json
import contextlib

# =============================================================================
# HOW TO USE
# -----------------------------------------------------------------------------
#
#  1. In PackageTesting.sublime-settings (can be placed anywhere under Packages),
#     define "active_tests" and give it the name of a package as its value.
#  2. Inside the package referenced in "active_tests", create a PackageTesting.json
#     file where you define settings like this:
#
#     {
#       "working_dir": "FooBarPackage",
#       "data": {
#         "main": "tests/data/main_test_data.txt"
#       },
#       "test_suites": {
#         "registers": ["package_testing_run_data_file_based_tests", "tests.test_registers"],
#         "settings": ["package_testing_run_data_file_based_tests", "tests.test_settings"],
#         "all with data file": ["package_testing_run_data_file_based_tests", ["tests.test_settings", "tests.test_registers"]]
#       }
#     }
# =============================================================================


@contextlib.contextmanager
def pushd(to):
    old_cwd = os.getcwdu()
    os.chdir(to)
    yield
    os.chdir(old_cwd)


class TestsSettings(object):
    def __init__(self):
        self._load_from_file()

    def _load_from_file(self):
        settings = sublime.load_settings('PackageTesting.sublime-settings')
        package_name = settings.get('active_tests')
        self.path_to_package = os.path.join(sublime.packages_path(), package_name)
        path_to_test_settings = os.path.join(sublime.packages_path(), package_name)
        data_json = json.load(open(os.path.join(path_to_test_settings, "PackageTesting.json")))
        self.path_to_data = os.path.join(sublime.packages_path(),
                                         data_json["working_dir"],
                                         data_json["data"]["main"])
        self.test_suites = data_json["test_suites"]


class TestsState(object):
    def __init__(self):
        self.test_suite_to_run = ''
        self.test_view = None
        self.test_suite_to_run = ''
        self._suites = []
        self.settings = TestsSettings()

    @property
    def must_run_tests(self):
        return len(self._suites) != 0

    def add_test_suite(self, name):
        # TODO(guillermooo): must enforce one type of test only (i.e. with test
        # data file or without.)
        self._suites.append(name)

    def iter_module_names(self):
        for name in self._suites:
            module_or_modules = self.settings.test_suites[name][1]
            if isinstance(module_or_modules, list):
                for item in module_or_modules:
                    yield item
            else:
                yield module_or_modules

    def run_all(self):
        for name in self._suites:
            cmd, _ = self.settings.test_suites[name]
            # XXX(guillermooo): this feels like cheating. improve this.
            sublime.active_window().run_command(cmd, dict(suite_name=name))

    def reset(self):
        self.test_suite_to_run = ''
        self.test_view = None
        self._suites = []


tests_state = TestsState()


def print_to_view(view, obtain_content):
    edit = view.begin_edit()
    view.insert(edit, 0, obtain_content())
    view.end_edit(edit)
    view.set_scratch(True)
    return view


class PackageTestingDisplayTestsCommand(sublime_plugin.WindowCommand):
    def run(self):
        tests_state.reset()
        self.window.show_quick_panel(sorted(tests_state.settings.test_suites.keys()), self.run_suite)

    def run_suite(self, idx):
        suite_name = sorted(tests_state.settings.test_suites.keys())[idx]
        tests_state.add_test_suite(suite_name)
        tests_state.run_all()


class PackageTestingRunSimpleTestsCommand(sublime_plugin.WindowCommand):
    def run(self, suite_name):
        with pushd(tests_state.settings.path_to_package):
            bucket = StringIO.StringIO()
            _, suite = tests_state.test_suites[suite_name]
            suite = unittest.defaultTestLoader.loadTestsFromName(suite)
            unittest.TextTestRunner(stream=bucket, verbosity=1).run(suite)

            print_to_view(self.window.new_file(), bucket.getvalue)


class PackageTestingRunDataFileBasedTestsCommand(sublime_plugin.WindowCommand):
    def run(self, suite_name):
        self.window.open_file(tests_state.settings.path_to_data)


class PackageTestingTestDataDispatcher(sublime_plugin.EventListener):
    def on_load(self, view):
        if not tests_state.must_run_tests:
            return

        with pushd(tests_state.settings.path_to_package):
            tests_state.test_view = view
            suite = unittest.TestLoader().loadTestsFromNames(tests_state.iter_module_names())

            bucket = StringIO.StringIO()
            unittest.TextTestRunner(stream=bucket, verbosity=1).run(suite)

            v = print_to_view(view.window().new_file(), bucket.getvalue)

        # Make this outside the with block or the __exit__ code will never
        # be executed due to the 'close' command.
        # In this order, or Sublime Text will fail.
        v.window().focus_view(view)
        view.window().run_command('close')
