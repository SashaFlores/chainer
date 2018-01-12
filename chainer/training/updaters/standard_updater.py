import six

from chainer.dataset import convert
from chainer.dataset import iterator as iterator_module
from chainer.training import _updater


class StandardUpdater(_updater.Updater):

    """Standard implementation of Updater.

    This is the standard implementation of :class:`Updater`. It accepts one or
    more training datasets and one or more optimizers. The default update
    routine assumes that there is only one training dataset and one optimizer.
    Users can override this update routine by inheriting this class and
    overriding the :meth:`update_core` method. Each batch is converted to input
    arrays by :func:`~chainer.datasets.concat_examples` by default, which can
    also be manually set by ``converter`` argument.

    Args:
        iterator: Dataset iterator for the training dataset. It can also be a
            dictionary that maps strings to iterators.
            If this is just an iterator, then the
            iterator is registered by the name ``'main'``.
        optimizer: Optimizer to update parameters. It can also be a dictionary
            that maps strings to optimizers.
            If this is just an optimizer, then the optimizer is
            registered by the name ``'main'``.
        converter: Converter function to build input arrays. Each batch
            extracted by the main iterator and the ``device`` option are passed
            to this function. :func:`~chainer.dataset.concat_examples` is used
            by default.
        device: Device to which the training data is sent. Negative value
            indicates the host memory (CPU).
        loss_func: Loss function. The target link of the main optimizer is used
            by default.
        loss_scale (float): Loss scaling factor. Loss scaling is a usefull
            technique to mitigate vanishing gradient issue that tends to happen
            when low precision data type like float16 is used during training.
            If you set loss scaling factor, gradients of loss values are to be
            multiplied by the factor before backprop starts. The factor is
            propagated to whole gradients in a computational graph along the
            backporp. The gradients of parameters are divided by the factor
            just before the parameters are to be updated.

    Attributes:
        converter: Converter function.
        loss_func: Loss function. If it is ``None``, the target link of the
                   main optimizer is used instead.
        device: Device to which the training data is sent.
        iteration: Current number of completed updates.

    """

    def __init__(self, iterator, optimizer, converter=convert.concat_examples,
                 device=None, loss_func=None, loss_scale=None):
        if isinstance(iterator, iterator_module.Iterator):
            iterator = {'main': iterator}
        self._iterators = iterator

        if not isinstance(optimizer, dict):
            optimizer = {'main': optimizer}
        self._optimizers = optimizer

        if device is not None and device >= 0:
            for optimizer in six.itervalues(self._optimizers):
                optimizer.target.to_gpu(device)

        self.converter = converter
        self.loss_func = loss_func
        self.device = device
        self.iteration = 0

        self.loss_scale = loss_scale
        for optimizer in six.itervalues(self._optimizers):
            optimizer.set_loss_scale(loss_scale)

    @property
    def epoch(self):
        return self._iterators['main'].epoch

    @property
    def epoch_detail(self):
        return self._iterators['main'].epoch_detail

    @property
    def previous_epoch_detail(self):
        return self._iterators['main'].previous_epoch_detail

    @property
    def is_new_epoch(self):
        return self._iterators['main'].is_new_epoch

    def finalize(self):
        """Finalizes the updater object.

        This method calls the `finalize` method of each iterator that
        this updater has.
        It is called at the end of training loops.

        """
        for iterator in six.itervalues(self._iterators):
            iterator.finalize()

    def get_optimizer(self, name):
        """Gets the optimizer of given name.

        Args:
            name (str): Name of the optimizer.

        Returns:
            ~chainer.Optimizer: Corresponding optimizer.

        """
        return self._optimizers[name]

    def get_all_optimizers(self):
        """Gets a dictionary of all optimizers for this updater.

        Returns:
            dict: Dictionary that maps names to optimizers.

        """
        return dict(self._optimizers)

    def get_iterator(self, name):
        """Gets the dataset iterator of given name.

        Args:
            name (str): Name of the dataset iterator.

        Returns:
            ~chainer.dataset.Iterator: Corresponding dataset iterator.

        """
        return self._iterators[name]

    def update(self):
        """Updates the parameters of the target model.

        This method implements an update formula for the training task,
        including data loading, forward/backward computations, and actual
        updates of parameters.

        This method is called once at each iteration of the training loop.

        """
        self.update_core()
        self.iteration += 1

    def update_core(self):
        batch = self._iterators['main'].next()
        in_arrays = self.converter(batch, self.device)

        optimizer = self._optimizers['main']
        loss_func = self.loss_func or optimizer.target

        if isinstance(in_arrays, tuple):
            optimizer.update(loss_func, *in_arrays)
        elif isinstance(in_arrays, dict):
            optimizer.update(loss_func, **in_arrays)
        else:
            optimizer.update(loss_func, in_arrays)

    def serialize(self, serializer):
        """Serializes the current state of the updater object."""
        for name, iterator in six.iteritems(self._iterators):
            iterator.serialize(serializer['iterator:' + name])

        for name, optimizer in six.iteritems(self._optimizers):
            optimizer.serialize(serializer['optimizer:' + name])
            optimizer.target.serialize(serializer['model:' + name])

        self.iteration = serializer('iteration', self.iteration)
