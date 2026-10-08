"""Write model channels in chunks, preserving the source LAS and point index."""
from pathlib import Path

import numpy as np


def write_prediction_las(source, values, output, channels, chunk_size=200_000):
    import laspy

    output = Path(output)
    partial = output.with_name(output.name + '.partial.las')
    if output.exists() or partial.exists():
        raise FileExistsError(output)
    channels = list(channels)
    if len(set(channels)) != len(channels) or chunk_size < 1:
        raise ValueError('Expected unique channels and a positive chunk size')
    with laspy.open(source) as reader:
        if len(values) != reader.header.point_count:
            raise ValueError('Prediction point count differs from source')
        header = reader.header.copy()
        source_dims = list(header.point_format.dimension_names)
        for channel in channels:
            if channel in source_dims or channel not in values.dtype.names:
                raise ValueError(f'Invalid model channel {channel}')
            header.add_extra_dim(laspy.ExtraBytesParams(name=channel, type=values.dtype.fields[channel][0]))
        index = 0
        with laspy.open(partial, mode='w', header=header) as writer:
            for original in reader.chunk_iterator(chunk_size):
                stop = index + len(original)
                predicted = values[index:stop]
                for las_name, pdal_name in (('x', 'X'), ('y', 'Y'), ('z', 'Z'), ('gps_time', 'GpsTime')):
                    if not np.array_equal(np.asarray(original[las_name]), predicted[pdal_name]):
                        raise ValueError(f'Prediction point order or source {las_name} differs')
                result = laspy.ScaleAwarePointRecord.zeros(len(original), header=header)
                for dimension in source_dims:
                    result[dimension] = original[dimension]
                for channel in channels:
                    result[channel] = predicted[channel]
                writer.write_points(result)
                index = stop
    partial.replace(output)
    return str(output)
