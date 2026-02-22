#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Time-stamp: <2019-11-06 15:27:12 vk>

import calendar
import html
import logging
import os
import pandoc
import re
import sys
import time

import feedparser
from orgformat import OrgFormat

from memacs.lib.memacs import Memacs
from memacs.lib.orgproperty import OrgProperties
from memacs.lib.reader import CommonReader


class RssMemacs(Memacs):
    def _parser_add_arguments(self):
        """
        overwritten method of class Memacs

        add additional arguments
        """
        Memacs._parser_add_arguments(self)

        self._parser.add_argument(
           "-u", "--url", dest="url",
           action="store",
           help="url to a rss file")

        self._parser.add_argument(
           "-f", "--file", dest="file",
           action="store",
           help="path to rss file")

        self._parser.add_argument(
            "--no-title", dest="no_title",
            action="store",
            default="skip",
            help="how to handle feed items with no title. Use 'skip' to ignore these items, 'notitle' to use '(No title)', or a positive integer to truncate the title at a word break before that number of characters.")

    def _parser_parse_args(self):
        """
        overwritten method of class Memacs

        all additional arguments are parsed in here
        """
        Memacs._parser_parse_args(self)
        if self._args.url and self._args.file:
            self._parser.error("you cannot set both url and file")

        if not self._args.url and not self._args.file:
            self._parser.error("please specify a file or url")

        if self._args.file:
            if not os.path.exists(self._args.file):
                self._parser.error("file %s not readable", self._args.file)
            if not os.access(self._args.file, os.R_OK):
                self._parser.error("file %s not readable", self._args.file)

        if self._args.no_title == "skip":
            self._skip_no_title = True
        else:
            self._skip_no_title = False

            if self._args.no_title == "notitle":
                self._truncate_description_to_title_length = 0
            else:
                try:
                    self._truncate_description_to_title_length = int(self._args.no_title)
                except ValueError:
                    self._parser.error("--no-title must either be 'skip' or an integer")

    def __get_item_data(self, item):
        """
        gets information out of <item>..</item>

        @return:  output, note, properties, tags
                  variables for orgwriter.append_org_subitem
        """
        try:
            # logging.debug(item)
            properties = OrgProperties()
            guid = item['id']
            if not guid:
                logging.error("got no id")

            unformatted_link = item['link']
            short_link = OrgFormat.link(unformatted_link, "link")

            noteSource = item['description']
            noteDoc = None
            try:
                noteDoc = pandoc.read(noteSource, format="html")
                note = pandoc.write(noteDoc, format="org")
            except RuntimeError:
                # Probably Pandoc is not installed.
                logging.info("Couldn't generate org format from RSS item's description. Probably pandoc is not installed.")
                note = html.unescape(noteSource)
            
            if "title" in item:
                # if we found a url in title
                # then append the url in front of subject
                title = item['title']
                try:
                    titleDoc = pandoc.read(title, format="html")
                    title = pandoc.write(titleDoc, format="org", options=["--wrap=none"])
                except RuntimeError:
                    # Again, probably just Pandoc is unavailable
                    pass
                
                if re.search("http[s]?://", title) is not None:
                    output = short_link + ": " + title
                else:
                    output = OrgFormat.link(unformatted_link, title)
            else:
                if self._skip_no_title:
                    logging.debug("No title for item; skipping")
                    return None, None, None, None, None
                
                if self._truncate_description_to_title_length > 0:
                    logging.debug("Generating title by shortening description")

                    notePlainText = note
                    if noteDoc:
                        try:
                            notePlainText = pandoc.write(noteDoc, format="plain")
                        except RuntimeError:
                            # Again, probably just missing Pandoc
                            logging.info("Couldn't convert note to plaintext to generate title; Probably pandoc is not installed.")

                    # The title should be at most this many characters long
                    if len(notePlainText) > self._truncate_description_to_title_length:
                        title = notePlainText[:self._truncate_description_to_title_length]

                        # Find the index of the beginning of the last bit
                        # of whitespace. If we find one, that's where we
                        # want to truncate. Otherwise we just let it
                        # truncate in the middle of a word.
                        matches = [x for x in re.finditer(r'\s+', title)]
                        if len(matches) > 0:
                            lastMatch = matches[-1]
                            if lastMatch:
                                title = title[:lastMatch.start()]

                        # Lastly, append an ellipsis.
                        title = f"{title}..."
                else:
                    logging.debug("Generating \"(No title)\"")
                    title = "(No title)"

                output = OrgFormat.link(unformatted_link, title)
                

            # converting updated_parsed UTC --> LOCALTIME
            # Karl 2018-09-22 this might be changed due to:
            # DeprecationWarning: To avoid breaking existing software
            # while fixing issue 310, a temporary mapping has been
            # created from `updated_parsed` to `published_parsed` if
            # `updated_parsed` doesn't exist. This fallback will be
            # removed in a future version of feedparser.
            timestamp = OrgFormat.date(
                time.localtime(calendar.timegm(item['updated_parsed'])), show_time=True)

            properties.add("guid", guid)

        except KeyError:
            logging.error("input is not a RSS 2.0")
            sys.exit(1)

        tags = []
        # Karl 2018-09-22 this might be changed due to:
        # DeprecationWarning: To avoid breaking existing software
        # while fixing issue 310, a temporary mapping has been created
        # from `updated_parsed` to `published_parsed` if
        # `updated_parsed` doesn't exist. This fallback will be
        # removed in a future version of feedparser.
        dont_parse = ['title', 'description', 'updated', 'summary',
                      'updated_parsed', 'link', 'links']
        for i in item:
            logging.debug(i)
            if i not in dont_parse:
                if (type(i) == str or type(i) == str) and \
                   type(item[i]) == str and item[i] != "":
                    if i == "id":
                        i = "guid"
                    properties.add(i, item[i])
                else:
                    if i == "tags":
                        for tag in item[i]:
                            logging.debug("found tag: %s", tag['term'])
                            tags.append(tag['term'])

        return output, note, properties, tags, timestamp

    def _main(self):
        """
        get's automatically called from Memacs class
        """
        # getting data
        if self._args.file:
            data = CommonReader.get_data_from_file(self._args.file)
        elif self._args.url:
            data = CommonReader.get_data_from_url(self._args.url)

        rss = feedparser.parse(data)
        logging.info("title: %s", rss['feed']['title'])
        logging.info("there are: %d entries", len(rss.entries))

        for item in rss.entries:
            logging.debug(item)
            output, note, properties, tags, timestamp = \
                self.__get_item_data(item)
            if output:
                self._writer.write_org_subitem(output=output,
                                               timestamp=timestamp,
                                               note=note,
                                               properties=properties,
                                               tags=tags)
