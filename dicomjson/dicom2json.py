#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
import json
import logging
from logging import config
from pathlib import Path
import cv2
import numpy as np
import yaml
from pydicom import dcmread
from pydicom.errors import InvalidDicomError
from constants import DicomConstants, JsonConstants, PngConstants

DEFAULT_OUTPUT_DIR = Path(__file__).parent / Path("output")

# Load logger configuration from YAML file
with open(Path(__file__).parent / Path("logger_config.yaml"), 'rt') as f:
    config_data = yaml.safe_load(f.read())
    config.dictConfig(config_data)
# Get basic logger
logger = logging.getLogger('root')


def my_json_dumps(data):
    """my_json_dumps
    JSON formatter

    Arguments:
        data {str} -- Data to JSON beautify

    Returns:
        str -- Data beautified
    """
    return json.dumps(data, indent=2, sort_keys=True)


@dataclass
class DicomConvertedData:
    """Class for keeping track of converted DICOM items"""
    image: str
    output: str
    template: str


def convert_dicom_to_data(input_file, remove_dicom_fields, converted_data):
    """
    Convert DICOM file to JSON using pydicom library

    Arguments:
        input_file {str} -- DICOM file location
        remove_dicom_fields {list} -- DICOM field name to not save in JSON
        converted_data {list} -- DicomConvertedData items list
    """
    try:
        dicom_dataset = dcmread(str(input_file))

        # Extract DICOM data
        rows = dicom_dataset.get('Rows')
        columns = dicom_dataset.get('Columns')
        pixel_data = dicom_dataset.get('PixelData')
        bits_stored = dicom_dataset.get('BitsStored')
        pixel_data_length = None
        pixel_data_expected_length = None
        if pixel_data and rows and columns and bits_stored:
            pixel_data_length = len(pixel_data)
            pixel_data_expected_length = rows * columns * (bits_stored / 8)

        # Format output filepath
        output_filepath = (DEFAULT_OUTPUT_DIR / input_file.stem)
        output_dataset_filepath = output_filepath.with_suffix(
            JsonConstants.SUFFIX.value)
        output_image_filepath = output_filepath.with_suffix(
            PngConstants.SUFFIX.value)

        # Remove DICOM fields specified by the user
        if remove_dicom_fields:
            for dicom_fields_name in remove_dicom_fields:
                if dicom_dataset.get(dicom_fields_name):
                    dicom_dataset.pop(dicom_fields_name)
                else:
                    dicom_error = "Unrecognized DICOM field named '{}'".format(
                        dicom_fields_name)
                    logger.warning(dicom_error)

        # Write dataset JSON file
        dicom_dataset_to_json_meta = dicom_dataset.file_meta.to_json_dict()
        dicom_dataset_to_json = dicom_dataset.to_json_dict()
        dicom_json_file = open(str(output_dataset_filepath), "w")
        dicom_json_file.write(my_json_dumps(
            {
                JsonConstants.META.value: dicom_dataset_to_json_meta,
                JsonConstants.DATA.value: dicom_dataset_to_json
            }))
        dicom_json_file.close()

        # Create image only if Rows, Columns, BitsStored and PixelData are filled
        if rows and columns and pixel_data and bits_stored:
            # Extract image from PixelData DICOM file
            img_dtype = None
            if bits_stored == 8:
                img_dtype = np.uint8
            elif bits_stored == 16:
                img_dtype = np.uint16
            else:
                bits_stored_error = "Unrecognized DICOM BitsStored value '{}'".format(
                    bits_stored)
                raise ValueError(bits_stored_error)

            # Check buffer size consistancy
            if not pixel_data_length == int(pixel_data_expected_length):
                logger.error("%s buffer size is not consistent",
                             str(input_file.resolve()))
                converted_data.append(DicomConvertedData(
                    None, input_file.name, str(output_dataset_filepath)))
                return

            # Write image PNG file
            dicom_image = np.ndarray((rows, columns),
                                     img_dtype,
                                     pixel_data)
            cv2.imwrite(str(output_image_filepath),
                        dicom_image)  # pylint: disable=E1101

            # Add full data in the main list
            converted_data.append(DicomConvertedData(
                str(output_image_filepath), input_file.name, str(output_dataset_filepath)))
        else:
            logger.warning("%s has no Rows or Columns or BitsStored or PixelData DICOM fields", str(
                input_file.resolve()))
            converted_data.append(DicomConvertedData(
                None, input_file.name, str(output_dataset_filepath)))
    except (FileNotFoundError,
            InvalidDicomError,
            PermissionError,
            UnboundLocalError) as error:
        raise error


def dicom2json(input_files, remove_dicom_fields):
    """
    Convert DICOM file to JSON using pydicom library

    Arguments:
        input_files {str} -- DICOM files location
        remove_dicom_fields {list} -- DICOM field name to not save in JSON
    """
    try:
        converted_data = []
        for input_file in input_files:
            logger.debug("Convert %s", str(input_file.resolve()))
            convert_dicom_to_data(
                input_file, remove_dicom_fields, converted_data)

        output_template_filepath = (DEFAULT_OUTPUT_DIR / Path("_dicom2json")).with_suffix(
            JsonConstants.SUFFIX.value)

        # Write template file
        converted_data_json_object = []
        for data in converted_data:
            converted_data_json_object.append({
                JsonConstants.TEMPLATE.value: data.template,
                JsonConstants.IMAGE.value: data.image,
                JsonConstants.OUTPUT.value: data.output
            })
        dicom_json_template_file = open(output_template_filepath, "w")
        dicom_json_template_file.write(
            my_json_dumps(converted_data_json_object))
        dicom_json_template_file.close()

        logger.debug("Output files for have been writed at: '%s'",
                     DEFAULT_OUTPUT_DIR)
    except (FileNotFoundError,
            InvalidDicomError,
            PermissionError,
            UnboundLocalError) as error:
        raise error


def main():
    """main
    Extract all informations from arguments parser
    If all mandatories data are provided, we launch
    the converter

    Returns:
        [int] -- Script exit code
    """
    parser = argparse.ArgumentParser()

    # Positional argument
    parser.add_argument(
        "input_files",
        nargs='+',
        type=str,
        help="dicom to convert to json, can be a directory!")

    # Optionals arguments
    remove_dicom_fields_help = "remove DICOM fields after extraction. \
        The list of possible values is available in the file '_dicom_dict.py' at \
            the root of the folder where the 'Keyword' for each field is specified."
    parser.add_argument(
        "-rdf",
        "--remove_dicom_fields",
        nargs='+',
        type=str,
        help=remove_dicom_fields_help,
        default=None)

    args = parser.parse_args()
    input_files = args.input_files
    remove_dicom_fields = args.remove_dicom_fields

    files = []
    for input_file in input_files:
        input_filepath = Path(input_file)
        if not input_filepath.exists():
            input_not_exists_error = "{} does not exists, abort dicom2json execution!".format(
                input_filepath)
            raise ValueError(input_not_exists_error)
        if input_filepath.is_file():
            files.append(input_filepath)
        elif input_filepath.is_dir():
            files.extend(list(input_filepath.glob(
                '*' + DicomConstants.SUFFIX.value)))
        else:
            input_is_not_file_error = "{} is not a file, abort dicom2json execution!".format(
                input_filepath)
            raise ValueError(input_is_not_file_error)

    try:
        dicom2json(files, remove_dicom_fields)
    except Exception as error:
        raise error


if __name__ == "__main__":
    """
    Entry point of the script
    """
    try:
        main()
        exit(0)
    except ValueError as error:
        logger.exception(error)
        exit(1)
