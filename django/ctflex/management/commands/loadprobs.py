import os
import re
import shutil
import sys
import textwrap
import traceback
from os.path import join, isfile, isdir

import yaml
from IPython.core import ultratb
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from ctflex.constants import UUID_REGEX
from ctflex.management.commands._common import add_debug, add_no_input, add_clear
from ctflex.models import CtfProblem, Window

PROBLEMS_DIR = settings.PROBLEMS_DIR
PROBLEMS_STATIC_DIR = settings.PROBLEMS_STATIC_DIR

PROBLEM_BASENAME = 'problem.yaml'
GRADER_BASENAME = 'grader.py'
STATIC_BASENAME = 'static'
UUID_BASENAME = '.uuid'
UUID_BACKUP_BASENAME = '.uuid.rejected'

PK_FIELD = 'id'


class Command(BaseCommand):
    help = "Add/Update problems"

    def add_arguments(self, parser):
        add_no_input(parser)
        add_debug(parser)
        add_clear(parser)

    def walk(self, directory):
        """Yield sub-directories that don't begin with an underscore"""

        # Walk over the directory
        self.stdout.write("Walking directory '{}'".format(directory))
        for basename in os.listdir(directory):
            self.stdout.write("")
            path = join(directory, basename)

            # Skip files
            if isfile(path):
                self.stdout.write("Ignoring '{}': Is file".format(basename))
                continue

            # Ignore private dirs
            if basename.startswith('_'):
                self.stdout.write("Ignoring '{}': Marked private with underscore".format(basename))
                continue

            yield basename, path

    def handle_error(self, err):
        if self.debug:
            raise err
        else:
            self.errors.append(sys.exc_info())

    def handle(self, **options):

        write = self.stdout.write

        # Check for debug mode
        self.debug = options['debug']
        if self.debug:
            sys.excepthook = ultratb.FormattedTB(mode='Verbose', color_scheme='Linux', call_pdb=1)
        else:
            self.errors = []

        # Get ready to track problem IDs
        processed_problems = []

        # Delete any existing files after confirmation
        if isdir(PROBLEMS_STATIC_DIR):
            message = textwrap.dedent("""\
                You have requested to load problems into the database and collect static files
                to the intermediate     location as specified in your settings:

                    {}

                This will DELETE ALL FILES in this location!
                Are you sure you want to do this?

                Type 'yes' to continue, or 'no' to cancel:\
                """.format(PROBLEMS_STATIC_DIR))
            if options['interactive'] and input(message) != "yes":
                raise CommandError("Loading problems cancelled.")
            write("Deleting all files in the intermediate location\n\n")
            shutil.rmtree(PROBLEMS_STATIC_DIR)
        os.makedirs(PROBLEMS_STATIC_DIR, exist_ok=True)

        # Rotate over window folders
        for window_basename, window_path in self.walk(PROBLEMS_DIR):
            for prob_basename, prob_path in self.walk(window_path):

                # Load problem file
                problem_filename = join(prob_path, PROBLEM_BASENAME)
                try:
                    with open(problem_filename) as problem_file:
                        data = yaml.load(problem_file)
                except (IsADirectoryError, FileNotFoundError) as err:
                    write("Skipping '{}': No problems file found".format(prob_basename))
                    self.handle_error(err)
                    continue
                data['grader'] = join(prob_path, GRADER_BASENAME)

                # Clean and warn about integer IDs
                if 'id' in data:
                    self.stderr.write(textwrap.dedent("""\
                        Warning: Integer IDs are obsolete and will be ignored.
                        Create/modify a {} file in folder '{}' instead.\
                        """.format(UUID_BASENAME, prob_basename)))
                    del data['id']

                # Check for and validate existing UUID file
                uuid_path = join(prob_path, UUID_BASENAME)
                if isfile(uuid_path):
                    with open(uuid_path) as uuid_file:
                        uuid = uuid_file.read().strip()
                        data[PK_FIELD] = uuid

                    if not re.match('{}$'.format(UUID_REGEX), uuid):
                        write("Error: UUID File did not match the expected format '{}'".format(UUID_REGEX))
                        uuid = None

                        write("Backing up and deleting existing UUID file")
                        backip_uuid_path = join(prob_path, UUID_BACKUP_BASENAME)
                        shutil.move(uuid_path, backip_uuid_path)
                else:
                    uuid = None

                # Add window and add defaults
                data['window'] = Window.objects.get(code=window_basename)
                data.setdefault('dynamic', None)
                data.setdefault('description', '')
                data.setdefault('hint', '')

                # If problem exists, update it
                query = CtfProblem.objects.filter(**{PK_FIELD: uuid})
                if uuid and query.exists():
                    write("Trying to update problem for '{}'".format(prob_basename))
                    problem = query.get()
                    for attr, value in data.items():
                        setattr(problem, attr, value)

                # Otherwise, create a new problem
                else:
                    write("Trying to create problem for '{}'".format(prob_basename))
                    problem = CtfProblem(**data)

                    # Save the UUID to a file
                    uuid = str(problem.id)
                    write("Creating a UUID file for '{}'".format(prob_basename))
                    with open(uuid_path, 'w') as uuid_file:
                        uuid_file.write(uuid)

                # Catch validation errors
                try:
                    problem.save()
                except ValidationError as err:
                    write("Validation failed for '{}'".format(prob_basename))
                    self.handle_error(err)
                    continue

                # Either way, copy over any static files
                try:
                    static_from = join(prob_path, STATIC_BASENAME)
                    static_to = join(PROBLEMS_STATIC_DIR, str(uuid))

                    # TODO(Yatharth): Hash filenames
                    if isdir(static_from):
                        write("Trying to copy static files from '{}'".format(prob_basename))
                        shutil.copytree(static_from, static_to)

                except (shutil.Error, IOError) as err:
                    write("Unable to copy static files for '{}'".format(prob_basename))
                    self.handle_error(err)
                    continue

                # Also, mark as processed
                processed_problems.append(problem.id)

                # We made it!
                write("Successfully imported problem for '{}'".format(prob_basename))

        # Delete existing problems that were not updated if clear option was given
        unprocessed_problems = CtfProblem.objects.exclude(pk__in=processed_problems).all()
        if options['clear'] and unprocessed_problems:
            message = textwrap.dedent("""\
                You have requested to delete all pre-existing problems that were not updated.
                Please review the list of problems to be deleted.

                    {}

                This will DELETE ALL THE LISTED PROBLEMS!
                Are you sure you want to do this?

                Type 'yes' to continue, or 'no' to cancel:\
                """.format(unprocessed_problems))
            if options['interactive'] and input(message) != "yes":
                raise CommandError("Loading problems cancelled.")
            write("\nDeleting all unprocessed problems\n\n")
            for problem in unprocessed_problems:
                problem.delete()

        # Print the stack traces from before if not already dealt with
        if not self.debug and self.errors:
            write("\nPrinting stacktraces of encountered exceptions")
            for err in self.errors:
                write(''.join(traceback.format_exception(*err)))
            raise RuntimeError("Exceptions encountered")
