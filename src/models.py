"""Model utilities for building and training LSTM forecasters."""

from __future__ import annotations

import logging
from typing import List, Sequence

import tensorflow as tf
from tensorflow.keras import callbacks, layers, models, optimizers
from tensorflow.keras.utils import register_keras_serializable

from .config import ModelConfig

TARGET_CLOSE_PENALTY = 4.0


@register_keras_serializable(package="CustomLosses")
def weighted_mse(y_true: tf.Tensor, y_pred: tf.Tensor) -> tf.Tensor:
    """
    Compute a horizon-weighted mean-squared error with terminal close emphasis.

    Args:
        y_true: Ground-truth targets with shape (batch, horizon).
        y_pred: Model predictions with the same shape as `y_true`.

    Returns:
        Scalar loss emphasising later forecast steps and the final compounded target.
    """
    horizon = tf.cast(tf.shape(y_true)[1], tf.float32)
    weights = tf.range(horizon, dtype=tf.float32)
    weights = 1.0 + 0.5 * weights
    weights = tf.reshape(weights, (1, -1))
    step_loss = tf.reduce_mean(tf.square(y_true - y_pred) * weights)

    safe_true = tf.maximum(1.0 + y_true, 1e-6)
    safe_pred = tf.maximum(1.0 + y_pred, 1e-6)
    true_terminal = tf.math.cumprod(safe_true, axis=1)[:, -1]
    pred_terminal = tf.math.cumprod(safe_pred, axis=1)[:, -1]
    terminal_loss = tf.reduce_mean(tf.square(true_terminal - pred_terminal))

    return step_loss + TARGET_CLOSE_PENALTY * terminal_loss


def resolve_loss(loss_name: str):
    """
    Translate a loss identifier into a TensorFlow-compatible object.

    Args:
        loss_name: Name from configuration (case-insensitive).

    Returns:
        A loss function or string understood by Keras.

    Raises:
        ValueError: If the loss is unsupported.
    """
    key = loss_name.lower()
    if key in {"weighted_mse", "weighted-mse"}:
        return weighted_mse
    if key in {"mse", "mean_squared_error"}:
        return "mse"
    if key in {"mae", "mean_absolute_error"}:
        return "mae"
    raise ValueError(f"Unsupported loss '{loss_name}'.")


def resolve_metrics(metrics: Sequence[str]):
    """
    Normalise metric identifiers for Keras compilation.

    Args:
        metrics: Iterable of metric names from configuration.

    Returns:
        List of metric identifiers suitable for `model.compile`.

    Raises:
        ValueError: If a metric is unknown.
    """
    resolved = []
    for metric in metrics:
        key = metric.lower()
        if key in {"mse", "mean_squared_error"}:
            resolved.append("mse")
        elif key in {"mae", "mean_absolute_error"}:
            resolved.append("mae")
        elif key in {"mape"}:
            resolved.append("mape")
        else:
            raise ValueError(f"Unsupported metric '{metric}'.")
    return resolved


class BaseForecaster:
    """Common functionality shared by forecasting architectures."""

    def __init__(self, config: ModelConfig, forecast_horizon: int):
        self.config = config
        self.forecast_horizon = forecast_horizon
        self.model: models.Model | None = None

    def _compile(self, model: models.Model) -> models.Model:
        loss = resolve_loss(self.config.loss)
        metrics = resolve_metrics(self.config.metrics)
        optimizer = optimizers.Adam(learning_rate=self.config.learning_rate)
        model.compile(optimizer=optimizer, loss=loss, metrics=metrics)
        return model

    def _build_model(self, input_shape) -> models.Model:  # pragma: no cover - abstract
        raise NotImplementedError

    def build(self, input_shape) -> models.Model:
        if self.model is None:
            self.model = self._build_model(input_shape)
            self._compile(self.model)
            self.model.summary(print_fn=logging.debug)
        return self.model

    def fit(
        self,
        X_train,
        y_train,
        X_val,
        y_val,
        cb: Sequence[callbacks.Callback] | None = None,
        verbose: int = 1,
    ) -> tf.keras.callbacks.History:
        if self.model is None:
            self.build((X_train.shape[1], X_train.shape[2]))
        callback_list: List[callbacks.Callback] = list(cb or [])
        history = self.model.fit(
            X_train,
            y_train,
            epochs=self.config.epochs,
            batch_size=self.config.batch_size,
            validation_data=(X_val, y_val),
            callbacks=callback_list,
            verbose=verbose,
        )
        return history

    def evaluate(self, X, y):
        if self.model is None:
            raise RuntimeError("Model has not been built.")
        return self.model.evaluate(X, y, verbose=0)

    def predict(self, X):
        if self.model is None:
            raise RuntimeError("Model has not been built.")
        return self.model.predict(X, verbose=0)

    def save(self, path):
        if self.model is None:
            raise RuntimeError("Model has not been built.")
        self.model.save(path)


class LSTMForecaster(BaseForecaster):
    """Stacked LSTM forecaster."""

    def _build_model(self, input_shape) -> models.Model:
        logging.debug("Building LSTM model with input shape %s", input_shape)
        model = models.Sequential(name="lstm_forecaster")
        model.add(layers.Input(shape=input_shape))
        for idx, units in enumerate(self.config.lstm_units):
            return_sequences = idx < len(self.config.lstm_units) - 1
            model.add(
                layers.LSTM(
                    units,
                    return_sequences=return_sequences,
                    dropout=self.config.dropout,
                    name=f"lstm_{idx}",
                )
            )
            model.add(layers.Dropout(self.config.dropout, name=f"dropout_{idx}"))
        model.add(layers.Dense(self.forecast_horizon, name="forecast"))
        return model


class Seq2SeqForecaster(BaseForecaster):
    """Encoder-decoder LSTM forecaster for short horizons."""

    def _build_model(self, input_shape) -> models.Model:
        logging.debug("Building Seq2Seq model with input shape %s", input_shape)
        inputs = layers.Input(shape=input_shape, name="encoder_inputs")

        encoder_units = self.config.lstm_units[0] if self.config.lstm_units else 128
        encoder_lstm = layers.LSTM(
            encoder_units,
            return_state=True,
            dropout=self.config.dropout,
            name="encoder_lstm",
        )
        _, state_h, state_c = encoder_lstm(inputs)

        decoder_units = encoder_units
        decoder_input = layers.RepeatVector(self.forecast_horizon, name="repeat_horizon")(state_h)
        decoder_lstm = layers.LSTM(
            decoder_units,
            return_sequences=True,
            dropout=self.config.dropout,
            name="decoder_lstm",
        )
        decoder_output = decoder_lstm(decoder_input, initial_state=[state_h, state_c])
        decoder_output = layers.TimeDistributed(layers.Dense(1), name="time_distributed_output")(decoder_output)
        outputs = layers.Flatten(name="forecast_flatten")(decoder_output)

        return models.Model(inputs=inputs, outputs=outputs, name="seq2seq_forecaster")


class TransformerForecaster(BaseForecaster):
    """Lightweight transformer-style forecaster."""

    def _build_model(self, input_shape) -> models.Model:
        logging.debug("Building Transformer model with input shape %s", input_shape)
        inputs = layers.Input(shape=input_shape, name="transformer_inputs")
        d_model = self.config.lstm_units[0] if self.config.lstm_units else max(32, input_shape[1])
        x = layers.Dense(d_model, name="input_projection")(inputs)
        x = layers.LayerNormalization(name="pre_norm")(x)

        num_heads = min(4, max(1, d_model // 32))
        key_dim = min(64, max(16, d_model // max(1, num_heads)))
        attn = layers.MultiHeadAttention(
            num_heads=num_heads,
            key_dim=key_dim,
            dropout=self.config.dropout,
            name="mha",
        )(x, x)
        x = layers.Add(name="attn_residual")([x, attn])
        x = layers.LayerNormalization(name="post_attn_norm")(x)

        ff_units = max(d_model, 64)
        ff = layers.Dense(ff_units, activation="relu", name="ffn_dense1")(x)
        ff = layers.Dropout(self.config.dropout, name="ffn_dropout")(ff)
        ff = layers.Dense(d_model, activation="relu", name="ffn_dense2")(ff)
        x = layers.Add(name="ffn_residual")([x, ff])
        x = layers.LayerNormalization(name="post_ffn_norm")(x)

        x = layers.GlobalAveragePooling1D(name="gap")(x)
        outputs = layers.Dense(self.forecast_horizon, name="forecast")(x)

        return models.Model(inputs=inputs, outputs=outputs, name="transformer_forecaster")


def create_forecaster(config: ModelConfig, forecast_horizon: int) -> BaseForecaster:
    """Factory producing a forecaster based on the configured model type."""

    model_type = (config.type or "lstm").lower()
    if model_type == "lstm":
        return LSTMForecaster(config, forecast_horizon)
    if model_type in {"seq2seq", "seq2seq_lstm"}:
        return Seq2SeqForecaster(config, forecast_horizon)
    if model_type in {"transformer", "attention"}:
        return TransformerForecaster(config, forecast_horizon)
    raise ValueError(f"Unsupported model type '{config.type}'.")
