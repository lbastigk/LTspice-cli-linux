from subprocess import call
import os
from tempfile import mkstemp
from shutil import move
import numpy as np
import subprocess
import config
import shutil


# ----------- Simulation controls ----------- #

def run_simulations(parameter_set=None, numerical_name_start=0):

    # Set appropriate variables according to the argument of parameter_set
    if parameter_set is not None:
        parameter = parameter_set[0]
        parameter_value_list = parameter_set[1]
        use_default_parameters = False
    else:
        use_default_parameters = True

    # Specify file paths
    file_path = config.LTSpice_asc_filename[:-4] # Use .asc file specified in config, but remove file ending
    file_path_generated = file_path + '_generated'
    spice_exe_path = config.LTSpice_executable_path

    # Create a list of the generated files
    output_filenames = []

    if not use_default_parameters:
        # Run a simulation for each parameter value in the parameter set
        for i, parameter_value in enumerate(parameter_value_list):
            # Set specified parameters
            if config.output_data_naming_convention == 'number':
                file_num = str(i + numerical_name_start)
                output_name = '0'*(3-len(file_num)) + file_num
                output_path = config.output_data_path + output_name
            else:
                output_path = config.output_data_path + parameter + '=' + str(parameter_value)
            output_filenames.append(output_path)
            set_parameters(file_path + '.asc', parameter, parameter_value)
            print('Starting simulation with the specified parameter: ' + parameter + '=' + str(parameter_value))
            # Run simulation
            simulate(spice_exe_path, file_path_generated)
            # Set header and cleanup the file
            output_header = 'SPICE simulation result. Parameters: ' + ', '.join(get_parameters(file_path_generated + '.asc')) + '\n' # Maybe not add the time variables
            #clean_raw_file(spice_exe_path, file_path_generated, output_path, output_header)
            move_raw_file(file_path, output_path)

    else:
        # Run a simulation with the preset values of the file
        output_path = config.output_data_path + 'result'
        print('Starting simulation.')
        simulate(spice_exe_path, file_path)
        # Set header and cleanup the file
        output_header = 'SPICE simulation result. Parameters: ' + ', '.join(get_parameters(file_path + '.asc')) + '\n' # Maybe not add the time variables
        #clean_raw_file(spice_exe_path, file_path, output_path, output_header)
        move_raw_file(file_path, output_path)


    # Return the list with names of the output filenames
    return output_filenames


def to_windows_path(unix_path):
    result = subprocess.run(['winepath', '-w', unix_path], capture_output=True, text=True)
    return result.stdout.strip()


def simulate(spice_exe_path, file_path):
    # Convert Unix paths to Windows-style paths for Wine
    wine_spice_path = to_windows_path(spice_exe_path)
    wine_base_path = to_windows_path(file_path)

    file_name = os.path.basename(file_path)
    print(f'Simulation starting: {file_name}.asc')

    # Append extensions to Wine-compatible base path
    asc_file = wine_base_path + '.asc'
    net_file = wine_base_path + '.net'
    raw_file_unix = file_path + '.raw'  # raw_file is checked on Unix filesystem

    print("Running command:", ['wine', wine_spice_path, '-netlist', asc_file])
    subprocess.call(['wine', wine_spice_path, '-netlist', asc_file])
    subprocess.call(['wine', wine_spice_path, '-b', '-ascii', net_file])

    if os.path.exists(raw_file_unix):
        size = os.path.getsize(raw_file_unix)
        print(f'Simulation finished: {file_name}.raw created ({size / 1000:.1f} kB)')
    else:
        print('Error: .raw file not created. Simulation may have failed.')

def move_raw_file(source_path, target_path):
    """
    Move the .raw file from source_path to target_path.
    Automatically appends '.raw' if not included in paths.
    """
    if not source_path.endswith('.raw'):
        source_path += '.raw'
    if not target_path.endswith('.raw'):
        target_path += '.raw'

    try:
        shutil.move(source_path, target_path)
        print(f'Raw file saved to: {target_path}')
    except FileNotFoundError:
        print(f'Error: Raw file not found at {source_path}')
    except Exception as e:
        print(f'Error moving raw file: {e}')


def clean_raw_file(spice_exe_path, file_path, output_path, output_header):

    # Try to open the requested file
    file_name = file_path
    try:
        f = open(file_path + '.raw', 'r', encoding='latin1')
    except IOError:
        # If the requested raw file is not found, simulations will be run,
        # assuming a that a corresponding LTspice schematic exists
        print('File not found: ' + file_name + '.raw')
        simulate(spice_exe_path, file_path)
        f = open(file_path + '.raw', 'r', encoding='latin1')

    print('Cleaning up file: ' + file_name + '.raw')

    reading_header = True
    data = []
    data_line = []

    for line_num, line in enumerate(f):

        if reading_header:
            if line_num == 4:
                number_of_vars = int(line.split(' ')[-1])
            if line_num == 5:
                number_of_points = int(line.split(' ')[-1])
            if line[:7] == 'Values:':
                reading_header = False
                header_length = line_num + 1
                continue
        else:
            data_line_num = (line_num - header_length) % number_of_vars
            if data_line_num in config.variable_numbering.values():
                data_line.append(line.split('\t')[-1].split('\n')[0])
            if data_line_num == number_of_vars - 1:
                data.append(data_line)
                data_line = []

    f.close()

    # Rearrange data
    variables = sorted(config.variable_numbering, key=config.variable_numbering.__getitem__)
    variables = np.array(variables)[config.preffered_sorting].tolist()
    data = np.array(data)[:, config.preffered_sorting]

    # Write data to file
    try:
        f = open(output_path, 'w+')
    except IOError:
        print('\nThe path specified for saving output data, \'' + config.output_data_path + '\', doesn\'t appear to exist.\nPlease check if the filepath set in \'config.py\' is correct.')
        exit(0)
    f.write(output_header)
    f.write('\t'.join(variables) + '\n')
    for line in data:
        f.write('\t'.join(line) + '\n')
    f.close()

    size = os.path.getsize(output_path)
    print('CSV file created: ' + output_path + ' (' + str(size/1000) + ' kB)')



# ----------- Parameter controls ----------- #

def parse_parameter_file(filename):

    cmd_list = []
    param_file = open(filename, 'r')

    for line in param_file:
        line = line.split()
        if len(line) == 0:
            continue
        try:
            cmd = line[0]
            if cmd[0] == '#':
                continue
            elif cmd.lower() == 'set':
                parameter = line[1]
                value = line[2]
                cmd_list.append(('s', parameter, value))
            elif cmd.lower() == 'run':
                parameter = line[1]
                values = line[2:]
                cmd_list.append(('r', parameter, values))
            else:
                return None # Syntax error
        except IndexError:
            return None # Syntax error

    return cmd_list

def set_parameters(file_path, param, param_val, overwrite=False):
    f, abs_path = mkstemp()
    with open(abs_path, 'w') as new_file:
        with open(file_path, encoding='latin1') as old_file:  # add encoding here
            for line in old_file:
                line_list = line.split(' ')
                if line_list[0] == 'TEXT':
                    for element_num, element in enumerate(line_list):
                        if element.split('=')[0] == param:
                            line_list[element_num] = param + '=' + str(param_val)
                    if line_list[-1][-1] != '\n':
                        line_list[-1] = line_list[-1] + '\n'
                    new_file.write(' '.join(line_list))
                else:
                    new_file.write(line)
    os.close(f)
    if overwrite:
        os.remove(file_path)
        move(abs_path, file_path)
    else:
        move(abs_path, file_path[:-4] + '_generated.asc')


def get_parameters(file_path):
    output_list = []
    with open(file_path, 'r', encoding='latin1') as f:
        for line in f:
            line_list = line.split()
            if line_list[0] == 'TEXT' and '!.param' in line_list:
                output_list.extend(line_list[line_list.index('!.param') + 1:])
    return output_list

