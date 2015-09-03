import argparse
from bs4 import BeautifulSoup
import re
import requests
from collections import defaultdict
from os import makedirs, path, sep
from os.path import join, isfile, isdir


def is_url_pdf(url):
    """ Returns a guess as to whether the URL points to a PDF """
    # Split on HTML url arguements
    url_split = re.split(r"\?|\&", url.split("/")[-1])
    return any(x == "type=pdf" or x.endswith(".pdf") for x in url_split) or url.endswith("/pdf")


def print_title(msg):
    print()
    print("*" * 10 + " %s " % msg + "*" * 10)


def clean_name(name):
    """ Cleans a name so that it could be file or directory name """
    name = name.strip()

    # Replace a file seperator + surrounding spaces with '-'
    space_or_sep = "[\s" + sep + "]*"
    regex_path_sep = space_or_sep + sep + space_or_sep
    name = re.sub(regex_path_sep, "-", name)

    # Replace spaces with underscores
    return re.sub(r"[\s,]+", '_', name)

def run():
    parser = argparse.ArgumentParser(description="Downloads bookmarked PDFs")
    parser.add_argument("bookmarks", help="location of chrome exported bookmarks")
    parser.add_argument("output", help="directory to download the PDFs, PDF will " +
                        "be downloaded in subfolders reflecting the bookmark's structure")
    parser.add_argument("-a", "--try-all", action="store_true", help="Download each " +
                        "link and test if its a PDF, otherwise only download links " +
                        "that appear to point to PDFs based on their URL")
    parser.add_argument("-s", "--show-pdfs", action="store_true", help="List bookmarks " +
                        "that appear to point to PDFs based on our URL heuristics")
    parser.add_argument("-n", "--show-non-pdfs", action="store_true",
                        help="List bookmarks that appear not to point to PDFs based on " +
                        "our URL heuristic")
    parser.add_argument("-e", "--ignore-errors", action="store_true", help="Continue " +
                        "when download errors occur, errors are listed when finished")
    parser.add_argument("-v", "--dont_verify", action="store_true", help="Don't  " +
                        "check SSL certificates, use at your own risk")
    args = parser.parse_args()

    with open(args.bookmarks) as f:
        data = f.read()
    parsed_html = BeautifulSoup(data, 'html.parser')

    # list of folder names (ex. ['dir1', 'dir2']) -> list of (name, link) in folder
    bookmarks = defaultdict(list)
    for ref in parsed_html.find_all("a"):
        folders = []
        title = clean_name(ref.text)
        link = ref["href"]
        for parent in ref.parents:
            # Check through parents to find the folder names
            if parent.name == "dl":
                first_sibling = next(parent.parent.children)
                if first_sibling.name == "h3":
                    folder = clean_name(first_sibling.text)
                    folders.append(folder)
        folders = folders[::-1]
        bookmarks[sep.join(folders)].append((title, link))

    sorted_folders = sorted(bookmarks.keys())
    if args.show_pdfs or args.show_non_pdfs:
        for key in sorted_folders:
            print_title(key)
            for title, link in bookmarks[key]:
                if (args.show_pdfs and is_url_pdf(link)) or\
                    args.show_non_pdfs and not is_url_pdf(link):
                    print("/".join(folders), title)
    else:
        if not isdir(args.output):
            raise ValueError("%s it not a directory" % args.output)
        total_booksmarks = sum(len(x) for x in bookmarks.values())

        errors = []
        on_bookmark = 0
        for folder in sorted_folders:
            print_title("Downloading %s" % folder)
            subfolder_path = join(args.output, folder)
            if not isdir(subfolder_path):
                makedirs(subfolder_path)
            for title, link in bookmarks[folder]:
                if not args.try_all and not is_url_pdf(link):
                    continue
                on_bookmark += 1
                pdf_path = join(subfolder_path, title + ".pdf")
                if isfile(pdf_path):
                    print("Already have %s" % pdf_path)
                    continue

                def record_error(msg):
                    if not args.ignore_errors:
                        raise ValueError(msg)
                    print("ERROR on %s: %s" % (title, msg))
                    errors.append((msg, link, title))

                print("Downloading %s (%d of %d)" % (pdf_path, on_bookmark, total_booksmarks))

                try:
                    r = requests.get(link, verify=not args.dont_verify)
                    r.raise_for_status()
                except Exception as e:
                    record_error("Download Exception: %s" % e)
                    continue

                content_type = r.headers["content-type"].split(";")
                if not any(x.endswith("pdf") for x in content_type):
                    record_error("Non PDF content type %s" % r.headers["content-type"])
                    continue

                content = r.content
                try:
                    # Be a bit paranoid in case a URL lied about its content type
                    if content.decode("utf-8").startswith("<!DOCTYPE html>"):
                        record_error("Appeared to get an HTML file" +
                                     " for doc %s url=%s" % (pdf_path, link))
                        continue
                except UnicodeDecodeError:
                    pass
                with open(pdf_path, "wb") as pdf_file:
                    pdf_file.write(content)
                    r.close()

        print("*" * 10 + " ALL ERRORS " + "*" * 10)
        for msg, link, title in errors:
            print("%s: %s\n%s" % (title, link, msg))

if __name__ == "__main__":
    run()
