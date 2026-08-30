import sys

def replace_version_in_app_state(version_code):
    with open('lib/app_state.dart', 'r') as file:
        lines = file.readlines()

    with open('lib/app_state.dart', 'w') as file:
        for line in lines:
            if 'String _appVersion =' in line:
                file.write(f'  String _appVersion = "{version_code}";\n')
            else:
                file.write(line)


def replace_version_in_actions(version_code):
    with open('lib/actions/actions.dart', 'r') as file:
        lines = file.readlines()

    with open('lib/actions/actions.dart', 'w') as file:
        for line in lines:
            if 'FFAppState().appVersion = ' in line:
                file.write(f"  FFAppState().appVersion = '{version_code}';\n")
            else:
                file.write(line)

def replace_version_in_yaml(version_name, version_code):
    with open('pubspec.yaml', 'r') as file:
        lines = file.readlines()

    with open('pubspec.yaml', 'w') as file:
        for line in lines:
            # Check if the line starts with "version:"
            if line.startswith('version:'):
                # Replace the line with the new version
                file.write(f'version: {version_name}+{version_code}\n')
            else:
                file.write(line)


def replace_signing_config_and_version_in_gradle(flutter_version_code, flutter_version_name):
    with open('android/app/build.gradle', 'r') as file:
        lines = file.readlines()

    with open('android/app/build.gradle', 'w') as file:
        for line in lines:
            # Replace "signingConfig signingConfigs.debug" with "signingConfig signingConfigs.release"
            if 'signingConfig signingConfigs.debug' in line:
                file.write(line.replace('signingConfigs.debug', 'signingConfigs.release'))
            # Replace flutterVersionCode and flutterVersionName
            elif 'flutterVersionCode' in line and "= '" in line:
                current_version = line.split("'")[1]
                file.write(line.replace(f"'{current_version}'", f"'{flutter_version_code}'"))
            elif 'flutterVersionName' in line and "= '" in line:
                current_version = line.split("'")[1]
                file.write(line.replace(f"'{current_version}'", f"'{flutter_version_name}'"))
            else:
                file.write(line)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <version_code>")
        sys.exit(1)

    version_name = sys.argv[1]
    flutter_version_code = sys.argv[2]
    replace_version_in_yaml(version_name, flutter_version_code)
    replace_version_in_app_state(version_name)
    replace_version_in_actions(version_name)
    print(f"Version updated to {version_name}+{flutter_version_code}  in pubspec.yaml")
    print(f"Version updated to {version_name} in app_state.dart")
    print(f"Version updated to {version_name} in actions.dart")


    replace_signing_config_and_version_in_gradle(flutter_version_code, version_name)
    print("Updated signingConfig from debug to release in build.gradle")
