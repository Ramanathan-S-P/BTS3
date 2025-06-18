import json
import sys
import os
import subprocess
import zipfile
import boto3
from datetime import datetime
from pathlib import Path

CONFIG_FILE = "db_configs.json"

# Global backup directory paths
BACKUP_PATHS = {
    'base': None,
    'mysql': None,
    'postgresql': None,
    'mongodb': None
}

def load_config(entity_id):
    try:
        with open(CONFIG_FILE) as f:
            configs = json.load(f)
        return configs[entity_id]
    except Exception as e:
        raise Exception(f"Config error: {e}")

"""def read_stdin_json():
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid input JSON: {str(e)}"}))
        sys.exit(1)
"""
def create_mysql_dump(config, dump_file):
    cmd = [
        "mysqldump",
        f"-h{config['host']}",
        f"-P{config.get('port', 3306)}",
        f"-u{config['user']}",
        f"-p{config['password']}",
        f"--result-file={dump_file}",
        config['database']
    ]


    process = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise Exception(process.stderr)
        
def create_postgresql_dump(config, dump_file):
    cmd = [
        "pg_dump",
        f"-h{config['host']}",
        f"-p{config.get('port', 5432)}",
        f"-U{config['user']}",
        f"--password={config['password']}",
        f"-f{dump_file}",
        config['database']
    ]

    process = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise Exception(process.stderr)

def create_mongodb_dump(config, dump_file):
    cmd = [
        "mongodump",
        f"--host={config['host']}",
        f"--username={config['user']}",
        f"--password={config['password']}",
        f"--db={config['database']}",
        f"--out={dump_file}"
    ]

    process = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        raise Exception(process.stderr)

def zip_file(input_path, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(input_path, arcname=os.path.basename(input_path))

def upload_to_s3(zip_path, s3_config):
    s3 = boto3.client(
        's3',
        aws_access_key_id=s3_config['access_key'],
        aws_secret_access_key=s3_config['secret_key']
    )

    bucket = s3_config['bucket']
    key = s3_config.get('object_key', os.path.basename(zip_path))

    s3.upload_file(zip_path, bucket, key)

def initialize_backup_directories():
    """Initialize backup directories in the BTS3 installation folder structure."""
    try:
        # Get the parent directory (BTS3 folder) from current script location
        current_dir = Path(os.path.dirname(os.path.abspath(__file__)))  # backend folder
        bts3_dir = current_dir.parent  # parent of backend is BTS3 folder
        base_dir = bts3_dir / 'backups'

        # Set up global paths
        BACKUP_PATHS['base'] = str(base_dir)
        BACKUP_PATHS['mysql'] = str(base_dir / 'mysql')
        BACKUP_PATHS['postgresql'] = str(base_dir / 'postgresql')
        BACKUP_PATHS['mongodb'] = str(base_dir / 'mongodb')

        # Create directories
        for path in BACKUP_PATHS.values():
            if path:  # Skip None values
                os.makedirs(path, exist_ok=True)

        return {"success": True, "message": "Backup directories initialized successfully"}
    except Exception as e:
        return {"success": False, "error": f"Failed to initialize backup directories: {str(e)}"}

def main():
    # Ensure backup directories are initialized
    if not any(BACKUP_PATHS.values()):
        result = initialize_backup_directories()
        if not result["success"]:
            print(json.dumps(result))
            return

    try:
        data = json.load(sys.stdin)
    
        entity_id = data["entity_id"]
        entity = load_config(entity_id)
        db_type = entity["db_type"]
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        # Use the global backup paths
        match db_type:
            case "mysql":
                dump_file = os.path.join(BACKUP_PATHS['mysql'], f"backup_{timestamp}.sql")
                zip_path = os.path.join(BACKUP_PATHS['mysql'], f"backup_{timestamp}.zip")
                create_mysql_dump(entity, dump_file)
                zip_file(dump_file, zip_path)
            case "postgresql":
                dump_file = os.path.join(BACKUP_PATHS['postgresql'], f"backup_{timestamp}.sql")
                zip_path = os.path.join(BACKUP_PATHS['postgresql'], f"backup_{timestamp}.zip")
                create_postgresql_dump(entity, dump_file)
                zip_file(dump_file, zip_path)    
            case "mongodb":
                dump_file = os.path.join(BACKUP_PATHS['mongodb'], f"backup_{timestamp}")
                zip_path = os.path.join(BACKUP_PATHS['mongodb'], f"backup_{timestamp}.zip")
                create_mongodb_dump(entity, dump_file)
                zip_file(dump_file, zip_path)
            case _:
                print(json.dumps({"success": False, "error": "Unsupported database type"}))
                return

            # Optionally upload to S3
        if data.get("s3", {}).get("enabled", False):
                upload_to_s3(zip_path, data["s3"])
                print(json.dumps({"success": True, "path": zip_path}))
    except Exception as e:
            print(json.dumps({"success": False, "error": str(e)}))
    finally:
            if 'dump_file' in locals() and os.path.exists(dump_file):
                os.remove(dump_file)
 

if __name__ == "__main__":
    main()
