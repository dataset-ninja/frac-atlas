import csv
import os
import shutil
from collections import defaultdict
from urllib.parse import unquote, urlparse

import supervisely as sly
from dataset_tools.convert import unpack_if_archive
from supervisely.io.fs import get_file_name, get_file_name_with_ext
from supervisely.io.json import load_json_file
from tqdm import tqdm

import src.settings as s


def download_dataset(teamfiles_dir: str) -> str:
    """Use it for large datasets to convert them on the instance"""
    api = sly.Api.from_env()
    team_id = sly.env.team_id()
    storage_dir = sly.app.get_data_dir()

    if isinstance(s.DOWNLOAD_ORIGINAL_URL, str):
        parsed_url = urlparse(s.DOWNLOAD_ORIGINAL_URL)
        file_name_with_ext = os.path.basename(parsed_url.path)
        file_name_with_ext = unquote(file_name_with_ext)

        sly.logger.info(f"Start unpacking archive '{file_name_with_ext}'...")
        local_path = os.path.join(storage_dir, file_name_with_ext)
        teamfiles_path = os.path.join(teamfiles_dir, file_name_with_ext)

        fsize = api.file.get_directory_size(team_id, teamfiles_dir)
        with tqdm(
            desc=f"Downloading '{file_name_with_ext}' to buffer...",
            total=fsize,
            unit="B",
            unit_scale=True,
        ) as pbar:
            api.file.download(team_id, teamfiles_path, local_path, progress_cb=pbar)
        dataset_path = unpack_if_archive(local_path)

    if isinstance(s.DOWNLOAD_ORIGINAL_URL, dict):
        for file_name_with_ext, url in s.DOWNLOAD_ORIGINAL_URL.items():
            local_path = os.path.join(storage_dir, file_name_with_ext)
            teamfiles_path = os.path.join(teamfiles_dir, file_name_with_ext)

            if not os.path.exists(get_file_name(local_path)):
                fsize = api.file.get_directory_size(team_id, teamfiles_dir)
                with tqdm(
                    desc=f"Downloading '{file_name_with_ext}' to buffer...",
                    total=fsize,
                    unit="B",
                    unit_scale=True,
                ) as pbar:
                    api.file.download(team_id, teamfiles_path, local_path, progress_cb=pbar)

                sly.logger.info(f"Start unpacking archive '{file_name_with_ext}'...")
                unpack_if_archive(local_path)
            else:
                sly.logger.info(
                    f"Archive '{file_name_with_ext}' was already unpacked to '{os.path.join(storage_dir, get_file_name(file_name_with_ext))}'. Skipping..."
                )

        dataset_path = storage_dir
    return dataset_path


def count_files(path, extension):
    count = 0
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith(extension):
                count += 1
    return count


def convert_and_upload_supervisely_project(
    api: sly.Api, workspace_id: int, project_name: str
) -> sly.ProjectInfo:
    ### Function should read local dataset and upload it to Supervisely project, then return project info.###
    images_path = "/home/alex/DATASETS/TODO/FracAtlas/FracAtlas/images/Fractured"
    not_fractured_images_path = "/home/alex/DATASETS/TODO/FracAtlas/FracAtlas/images/Non_fractured"
    json_path = "/home/alex/DATASETS/TODO/FracAtlas/FracAtlas/Annotations/COCO JSON/COCO_fracture_masks.json"

    train_split_path = (
        "/home/alex/DATASETS/TODO/FracAtlas/FracAtlas/Utilities/Fracture Split/train.csv"
    )
    val_split_path = (
        "/home/alex/DATASETS/TODO/FracAtlas/FracAtlas/Utilities/Fracture Split/valid.csv"
    )
    test_split_path = (
        "/home/alex/DATASETS/TODO/FracAtlas/FracAtlas/Utilities/Fracture Split/test.csv"
    )

    tags_path = "/home/alex/DATASETS/TODO/FracAtlas/FracAtlas/dataset.csv"

    batch_size = 10

    def create_ann(image_path):
        labels = []
        tags = []

        # image_np = sly.imaging.image.read(image_path)[:, :, 0]
        image_name = get_file_name_with_ext(image_path)
        img_height, img_wight = image_name_to_shape[image_name]

        ann_data = image_name_to_ann_data[get_file_name_with_ext(image_path)]
        for curr_ann_data in ann_data:
            polygons_coords = curr_ann_data[0]
            for coords in polygons_coords:
                exterior = []
                for i in range(0, len(coords), 2):
                    exterior.append([int(coords[i + 1]), int(coords[i])])
                if len(exterior) < 3:
                    continue
                poligon = sly.Polygon(exterior)
                label_poly = sly.Label(poligon, obj_class)
                labels.append(label_poly)

            bbox_coord = curr_ann_data[1]
            rectangle = sly.Rectangle(
                top=int(bbox_coord[1]),
                left=int(bbox_coord[0]),
                bottom=int(bbox_coord[1] + bbox_coord[3]),
                right=int(bbox_coord[0] + bbox_coord[2]),
            )
            label_rectangle = sly.Label(rectangle, obj_class)
            labels.append(label_rectangle)

        tags_data = image_name_to_tags[image_name]
        for index, tag_index in enumerate(tags_data):
            if tag_index == "1":
                tag_name = tags_names[index]
                tag_meta = meta.get_tag_meta(tag_name)
                tag = sly.Tag(tag_meta)
                tags.append(tag)

        return sly.Annotation(img_size=(img_height, img_wight), labels=labels, img_tags=tags)

    project = api.project.create(workspace_id, project_name, change_name_if_conflict=True)
    obj_class = sly.ObjClass("fractured", sly.AnyGeometry)

    tags_names = [
        "hand",
        "leg",
        "hip",
        "shoulder",
        "mixed",
        "hardware",
        "multiscan",
        "fractured",
        "fracture_count",
        "frontal",
        "lateral",
        "oblique",
    ]

    meta = sly.ProjectMeta(obj_classes=[obj_class])

    for tag_name in tags_names:
        tag_meta = sly.TagMeta(tag_name, sly.TagValueType.NONE)
        meta = meta.add_tag_meta(tag_meta)

    api.project.update_meta(project.id, meta.to_json())

    train_names = []
    with open(train_split_path, "r") as file:
        csvreader = csv.reader(file)
        for idx, row in enumerate(csvreader):
            if idx == 0:
                continue
            train_names.append(row[0])

    val_names = []
    with open(val_split_path, "r") as file:
        csvreader = csv.reader(file)
        for idx, row in enumerate(csvreader):
            if idx == 0:
                continue
            val_names.append(row[0])

    test_names = []
    with open(test_split_path, "r") as file:
        csvreader = csv.reader(file)
        for idx, row in enumerate(csvreader):
            if idx == 0:
                continue
            test_names.append(row[0])

    ds_name_to_images = {"train": train_names, "val": val_names, "test": test_names}

    image_name_to_tags = {}
    with open(tags_path, "r") as file:
        csvreader = csv.reader(file)
        for idx, row in enumerate(csvreader):
            if idx == 0:
                continue
            image_name_to_tags[row[0]] = row[1:]

    image_id_to_name = {}
    image_name_to_shape = {}
    image_name_to_ann_data = defaultdict(list)

    ann = load_json_file(json_path)
    for curr_image_info in ann["images"]:
        image_name_to_shape[curr_image_info["file_name"]] = (
            curr_image_info["height"],
            curr_image_info["width"],
        )
        image_id_to_name[curr_image_info["id"]] = curr_image_info["file_name"]

    for curr_ann_data in ann["annotations"]:
        image_id = curr_ann_data["image_id"]
        image_name_to_ann_data[image_id_to_name[image_id]].append(
            [curr_ann_data["segmentation"], curr_ann_data["bbox"]]
        )

    for ds_name, images_names in ds_name_to_images.items():
        dataset = api.dataset.create(project.id, ds_name, change_name_if_conflict=True)

        progress = sly.Progress("Create dataset {}".format(ds_name), len(images_names))

        for img_names_batch in sly.batched(images_names, batch_size=batch_size):
            images_pathes_batch = [
                os.path.join(images_path, image_path) for image_path in img_names_batch
            ]

            img_infos = api.image.upload_paths(dataset.id, img_names_batch, images_pathes_batch)
            img_ids = [im_info.id for im_info in img_infos]

            anns_batch = [create_ann(image_path) for image_path in images_pathes_batch]
            api.annotation.upload_anns(img_ids, anns_batch)

            progress.iters_done_report(len(img_names_batch))

    # ===================== Non_fractured ==========================

    dataset = api.dataset.create(project.id, "not fractured", change_name_if_conflict=True)
    images_names = os.listdir(not_fractured_images_path)
    progress = sly.Progress("Create dataset {}".format("not fractured"), len(images_names))

    for img_names_batch in sly.batched(images_names, batch_size=batch_size):
        images_pathes_batch = [
            os.path.join(not_fractured_images_path, image_path) for image_path in img_names_batch
        ]

        img_infos = api.image.upload_paths(dataset.id, img_names_batch, images_pathes_batch)
        img_ids = [im_info.id for im_info in img_infos]

        progress.iters_done_report(len(img_names_batch))

    return project
