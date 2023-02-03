'''
Implement the method to get relative clean result
'''
import numpy as np
import matplotlib.pyplot as plt
from sklearn.svm import SVR, SVC
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score
def dot_plot(cosine, y, correct_cosine):
    check = np.argmax(cosine, axis=-1) == y
    print(np.sum(check)/total, np.sum(check) / np.shape(check)[0])
    plt.scatter(np.arange(0, y.shape[0])[check], correct_cosine[check], c='r')
    plt.scatter(np.arange(0, y.shape[0])[~check], correct_cosine[~check], c='b')
    plt.show()


if __name__ == "__main__":
    embed = np.load('save_embedding.npz')
    audio = embed['audio']
    image = embed['image']
    text = embed['text']
    y = embed['y']

    total = y.shape[0]
    cosine = image @ text.transpose()
    correct_cosine = cosine[np.arange(total), y]

    # without selection
    # dot_plot(cosine, y, correct_cosine)

    # select by the threshold
    # above_threshold = correct_cosine > 0.2
    # dot_plot(cosine[above_threshold], y[above_threshold], correct_cosine[above_threshold])

    # select by skewness
    sort_cosine = np.sort(cosine, axis=-1)
    top_cos = sort_cosine[:, -1]
    top_ratio = sort_cosine[:, -1] / sort_cosine[:, -2]
    gap = np.mean(sort_cosine[:, -3:], axis=-1) - np.mean(sort_cosine[:, :-3], axis=-1)
    mean = np.mean(sort_cosine, axis=-1)
    var = np.var(sort_cosine, axis=-1)
    # # above_threshold = gap > 0.1
    # above_threshold = top_ratio > 1.1
    # dot_plot(cosine[above_threshold], y[above_threshold], correct_cosine[above_threshold])


    features = np.stack([top_cos, top_ratio, gap, mean, var], axis=1)
    cls = np.argmax(cosine, axis=-1) == y
    X_train, X_test, y_train, y_test = train_test_split(features, cls, test_size=0.2, random_state=42)

    clf = LogisticRegression(class_weight='balanced').fit(X_train, y_train)
    above_threshold = clf.predict(X_test)
    print(balanced_accuracy_score(above_threshold, y_test))
    # dot_plot(cosine[above_threshold], y[above_threshold], correct_cosine[above_threshold])

